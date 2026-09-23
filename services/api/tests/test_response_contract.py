import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.main import app
from app.core.dependencies import get_current_user
from app.core.security import create_token

NO_BODY_EXCEPTIONS = {
    ("DELETE", "/api/users/{user_id}"),
    ("DELETE", "/api/suppliers/{supplier_id}"),
}

FILE_RESPONSE_EXCEPTIONS = {
    ("GET", "/api/incidents/results/export"),
}

FOUNDATION_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _json_routes():
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            if route.path in FOUNDATION_ROUTES:
                continue
            if (method, route.path) in NO_BODY_EXCEPTIONS or (method, route.path) in FILE_RESPONSE_EXCEPTIONS:
                continue
            yield method, route.path, route


class TestExplicitResponseSerializers:
    def test_all_json_routes_declare_response_model(self):
        missing = []
        for method, path, route in _json_routes():
            if getattr(route, "response_model", None) is None:
                missing.append(f"{method} {path}")
        assert not missing, f"Endpoints sin response_model: {missing}"

    def test_no_response_model_exposes_password_or_hash(self):
        exposed = []
        for method, path, route in _json_routes():
            model = getattr(route, "response_model", None)
            if model is None:
                continue
            field_names = set(getattr(model, "model_fields", {}))
            for forbidden in ("hashed_password", "password", "password_changed_at"):
                if forbidden in field_names:
                    exposed.append(f"{method} {path} -> {forbidden}")
        assert not exposed, f"Campos sensibles expuestos en response_model: {exposed}"


class TestCurrentUserWhitelist:
    def test_get_current_user_returns_safe_fields(self):
        token = create_token({"sub": "1", "role": "admin"})
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        ctx = get_current_user(creds)
        assert set(ctx.keys()) == {"id", "email", "is_active", "role", "created_at"}
        assert "hashed_password" not in ctx
        assert "password_changed_at" not in ctx
        assert ctx["email"] == "admin@test.com"


@pytest.fixture(autouse=True)
def _clean_suppliers():
    from database import get_tinydb

    db = get_tinydb()
    db.table("suppliers").truncate()
    db.close()
    yield
    db = get_tinydb()
    db.table("suppliers").truncate()
    db.close()


class TestSlimListPayloads:
    def test_suppliers_list_returns_slim_payload(self, client, auth_headers):
        from database import get_tinydb

        db = get_tinydb()
        db.table("suppliers").insert({
            "name": "Acme",
            "country": "USA",
            "categories": ["carrier_last_mile"],
            "rate_per_shipment": 2.5,
            "currency": "USD",
            "updated_at": "2025-01-01T00:00:00+00:00",
            "status": "active",
            "service_zone": "West",
            "contact_email": "acme@example.com",
            "notes": "nota interna",
        })
        db.close()

        res = client.get("/api/suppliers", headers=auth_headers)
        assert res.status_code == 200
        item = res.json()[0]
        assert set(item.keys()) == {
            "id", "name", "country", "categories", "rate_per_shipment",
            "currency", "status", "contact_email",
        }
        assert "notes" not in item
        assert "service_zone" not in item
        assert "updated_at" not in item
        assert item["contact_email"] == "acme@example.com"

    def test_incidents_list_returns_excerpt_not_full_description(self, client, auth_headers):
        payload = {
            "title": "Incidente largo",
            "description": "x" * 300,
            "origin": "customer",
            "branch": "la_warehouse",
            "category": "lost_parcel",
        }
        created = client.post("/api/incidents", headers=auth_headers, json=payload)
        assert created.status_code == 201

        res = client.get("/api/incidents", headers=auth_headers)
        assert res.status_code == 200
        item = res.json()[0]
        assert set(item.keys()) == {
            "id", "title", "description_excerpt", "origin", "branch", "category", "status",
        }
        assert "description" not in item
        assert "created_at" not in item
        assert item["description_excerpt"].endswith("…")
        assert len(item["description_excerpt"]) <= 121

        detail = client.get(f"/api/incidents/{item['id']}", headers=auth_headers)
        assert detail.json()["description"] == payload["description"]