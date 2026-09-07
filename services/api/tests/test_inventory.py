import pytest

from sqlmodel import Session, delete, select

from database import engine
from models import SKU, StockEntry, StockExit
from app.services.inventory_service import compute_stock, compute_stock_by_warehouse

WAREHOUSES = ("los_angeles", "zaragoza")


@pytest.fixture(autouse=True)
def _clean_inventory(client):
    with Session(engine) as session:
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(delete(StockExit))
        session.exec(delete(StockEntry))
        session.exec(delete(SKU))
        session.commit()


@pytest.fixture()
def sql_session(client):
    with Session(engine) as session:
        yield session


def _create_product(client, auth_headers, name="Test SKU", sku_code="CLT-TEST-1", warehouse="los_angeles"):
    res = client.post(
        "/inventory/products",
        headers=auth_headers,
        json={"name": name, "sku_code": sku_code, "warehouse": warehouse},
    )
    assert res.status_code == 201
    return res.json()


def _create_order(client, auth_headers, order_type, sku_id, quantity, warehouse):
    res = client.post(
        f"/inventory/orders/{order_type}",
        headers=auth_headers,
        json={"sku_id": sku_id, "quantity": quantity, "warehouse": warehouse},
    )
    return res


def _product_stock(client, auth_headers, product_id):
    res = client.get(f"/inventory/products/{product_id}", headers=auth_headers)
    assert res.status_code == 200
    return res.json()


class TestStockCalculation:
    def test_compute_stock_per_warehouse_different(self, client, auth_headers, sql_session):
        sku = _create_product(client, auth_headers)
        sku_id = sku["id"]
        _create_order(client, auth_headers, "inbound", sku_id, 10, "los_angeles")
        _create_order(client, auth_headers, "inbound", sku_id, 5, "zaragoza")
        _create_order(client, auth_headers, "outbound", sku_id, 3, "los_angeles")

        assert compute_stock(sql_session, sku_id, "los_angeles") == 7
        assert compute_stock(sql_session, sku_id, "zaragoza") == 5

    def test_compute_stock_by_warehouse_returns_both(self, client, auth_headers, sql_session):
        sku = _create_product(client, auth_headers)
        sku_id = sku["id"]
        _create_order(client, auth_headers, "inbound", sku_id, 10, "los_angeles")
        _create_order(client, auth_headers, "inbound", sku_id, 4, "zaragoza")

        assert compute_stock_by_warehouse(sql_session, sku_id) == {
            "los_angeles": 10,
            "zaragoza": 4,
        }


class TestStockChanges:
    def test_inbound_increments_warehouse_stock(self, client, auth_headers):
        sku = _create_product(client, auth_headers)
        sku_id = sku["id"]

        res = _create_order(client, auth_headers, "inbound", sku_id, 10, "los_angeles")
        assert res.status_code == 201

        body = _product_stock(client, auth_headers, sku_id)
        assert body["current_stock_by_warehouse"]["los_angeles"] == 10
        assert body["current_stock_by_warehouse"]["zaragoza"] == 0

    def test_outbound_decrements_warehouse_stock(self, client, auth_headers):
        sku = _create_product(client, auth_headers)
        sku_id = sku["id"]
        _create_order(client, auth_headers, "inbound", sku_id, 10, "los_angeles")

        res = _create_order(client, auth_headers, "outbound", sku_id, 4, "los_angeles")
        assert res.status_code == 201

        body = _product_stock(client, auth_headers, sku_id)
        assert body["current_stock_by_warehouse"]["los_angeles"] == 6

    def test_orders_are_warehouse_scoped(self, client, auth_headers):
        sku = _create_product(client, auth_headers)
        sku_id = sku["id"]
        _create_order(client, auth_headers, "inbound", sku_id, 10, "los_angeles")

        _create_order(client, auth_headers, "inbound", sku_id, 3, "zaragoza")

        body = _product_stock(client, auth_headers, sku_id)
        assert body["current_stock_by_warehouse"]["los_angeles"] == 10
        assert body["current_stock_by_warehouse"]["zaragoza"] == 3


class TestOutboundValidation:
    def test_outbound_exceeding_stock_returns_400_and_writes_nothing(
        self, client, auth_headers, sql_session
    ):
        sku = _create_product(client, auth_headers)
        sku_id = sku["id"]
        _create_order(client, auth_headers, "inbound", sku_id, 5, "los_angeles")

        exits_before = len(sql_session.exec(select(StockExit)).all())

        res = _create_order(client, auth_headers, "outbound", sku_id, 10, "los_angeles")
        assert res.status_code == 400
        assert "Stock insuficiente" in res.json()["detail"]

        exits_after = len(sql_session.exec(select(StockExit)).all())
        assert exits_after == exits_before

        body = _product_stock(client, auth_headers, sku_id)
        assert body["current_stock_by_warehouse"]["los_angeles"] == 5


class TestOrderValidation:
    def test_quantity_zero_returns_validation_error(self, client, auth_headers):
        sku = _create_product(client, auth_headers)
        res = _create_order(client, auth_headers, "inbound", sku["id"], 0, "los_angeles")
        assert res.status_code == 422

    def test_quantity_negative_returns_validation_error(self, client, auth_headers):
        sku = _create_product(client, auth_headers)
        res = _create_order(client, auth_headers, "outbound", sku["id"], -5, "los_angeles")
        assert res.status_code == 422

    def test_invalid_warehouse_returns_400(self, client, auth_headers):
        sku = _create_product(client, auth_headers)
        res = _create_order(client, auth_headers, "inbound", sku["id"], 5, "madrid")
        assert res.status_code == 400
        assert "warehouse" in res.json()["detail"]

    def test_unknown_sku_returns_404(self, client, auth_headers):
        res = _create_order(client, auth_headers, "inbound", 99999, 5, "los_angeles")
        assert res.status_code == 404
        assert "99999" in res.json()["detail"]


class TestAuth:
    def test_get_products_without_token_returns_401(self, client):
        assert client.get("/inventory/products").status_code == 401

    def test_get_orders_without_token_returns_401(self, client):
        assert client.get("/inventory/orders").status_code == 401

    def test_inbound_with_user_role_returns_403(self, client, user_headers):
        res = client.post(
            "/inventory/orders/inbound",
            headers=user_headers,
            json={"sku_id": 1, "quantity": 5, "warehouse": "los_angeles"},
        )
        assert res.status_code == 403

    def test_get_products_with_normal_user_returns_200(self, client, user_headers):
        assert client.get("/inventory/products", headers=user_headers).status_code == 200


class TestOrdersEndpoint:
    def test_orders_return_explicit_mapping(self, client, auth_headers):
        sku = _create_product(client, auth_headers, name="Classic Sneaker", sku_code="CLT-SNK-1")
        sku_id = sku["id"]
        _create_order(client, auth_headers, "inbound", sku_id, 10, "los_angeles")
        _create_order(client, auth_headers, "outbound", sku_id, 3, "los_angeles")

        res = client.get("/inventory/orders", headers=auth_headers)
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 2

        expected_keys = {
            "id", "order_type", "sku_id", "product_name",
            "warehouse", "quantity", "user_uuid", "created_at",
        }
        by_type = {item["order_type"]: item for item in items}
        assert set(by_type) == {"inbound", "outbound"}

        for item in items:
            assert set(item.keys()) == expected_keys
            assert item["product_name"] == "Classic Sneaker"
            assert item["user_uuid"] == "1"

        assert by_type["inbound"]["quantity"] == 10
        assert by_type["inbound"]["warehouse"] == "los_angeles"
        assert by_type["outbound"]["quantity"] == 3