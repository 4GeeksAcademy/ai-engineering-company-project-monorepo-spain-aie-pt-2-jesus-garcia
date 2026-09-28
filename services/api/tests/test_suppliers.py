import pytest

from database import get_tinydb


@pytest.fixture(autouse=True)
def _clean_suppliers():
    db = get_tinydb()
    db.table("suppliers").truncate()
    db.close()
    yield
    db = get_tinydb()
    db.table("suppliers").truncate()
    db.close()


def _create(client, headers, name="Acme", country="USA", category="carrier_last_mile"):
    res = client.post(
        "/api/suppliers",
        headers=headers,
        json={
            "name": name,
            "country": country,
            "categories": [category],
            "rate_per_shipment": 2.5,
        },
    )
    assert res.status_code == 201
    return res.json()


class TestSuppliersCache:
    def test_list_cached_and_invalidated_on_create(self, client, auth_headers):
        from app.core.cache import cache

        _create(client, auth_headers)
        res = client.get("/api/suppliers", headers=auth_headers)
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert cache.get("suppliers:list:|||") is not None

        _create(client, auth_headers, name="Beta")
        assert cache.get("suppliers:list:|||") is None
        res = client.get("/api/suppliers", headers=auth_headers)
        assert len(res.json()) == 2

    def test_filters_use_distinct_keys_and_are_invalidated(self, client, auth_headers):
        from app.core.cache import cache

        _create(client, auth_headers)
        client.get("/api/suppliers?country=USA", headers=auth_headers)
        client.get("/api/suppliers?category=carrier_last_mile", headers=auth_headers)
        assert cache.get("suppliers:list:USA|||") is not None
        assert cache.get("suppliers:list:|carrier_last_mile||") is not None

        _create(client, auth_headers, name="Beta")
        assert cache.get("suppliers:list:USA|||") is None
        assert cache.get("suppliers:list:|carrier_last_mile||") is None

    def test_detail_cached_and_invalidated_on_update(self, client, auth_headers):
        from app.core.cache import cache

        supplier = _create(client, auth_headers)
        detail = client.get(
            f"/api/suppliers/{supplier['id']}", headers=auth_headers
        ).json()
        assert detail["name"] == "Acme"
        key = f"suppliers:detail:{supplier['id']}"
        assert cache.get(key) is not None

        res = client.put(
            f"/api/suppliers/{supplier['id']}",
            headers=auth_headers,
            json={"name": "Renamed"},
        )
        assert res.status_code == 200
        assert cache.get(key) is None

        updated = client.get(
            f"/api/suppliers/{supplier['id']}", headers=auth_headers
        ).json()
        assert updated["name"] == "Renamed"

    def test_delete_invalidates_cache(self, client, auth_headers):
        from app.core.cache import cache

        supplier = _create(client, auth_headers)
        client.get("/api/suppliers", headers=auth_headers)
        client.get(f"/api/suppliers/{supplier['id']}", headers=auth_headers)
        assert cache.get("suppliers:list:|||") is not None

        res = client.delete(f"/api/suppliers/{supplier['id']}", headers=auth_headers)
        assert res.status_code == 204
        assert cache.get("suppliers:list:|||") is None