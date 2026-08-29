from app.core.security import create_token


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


class TestProfiles:
    def test_get_profile_after_register(self, client, user_headers, register_user):
        payload, created = register_user
        res = client.get("/api/profiles/me", headers=user_headers)
        assert res.status_code == 200
        profile = res.json()
        assert profile["name"] == "Test User"
        assert profile["phone"] == "+34 600 000000"
        assert profile["user_id"] == created.json()["id"]

    def test_update_name_keeps_user_unchanged(self, client, user_headers, register_user):
        payload, _ = register_user
        res = client.put("/api/profiles/me", headers=user_headers, json={"name": "Nuevo Nombre"})
        assert res.status_code == 200
        assert res.json()["name"] == "Nuevo Nombre"

        me = client.get("/api/auth/me", headers=user_headers)
        assert me.status_code == 200
        assert me.json()["email"] == payload["email"]
        assert me.json()["profile"]["name"] == "Nuevo Nombre"

    def test_update_phone_to_empty_preserves_other_fields(self, client, user_headers):
        res = client.put("/api/profiles/me", headers=user_headers, json={"phone": ""})
        assert res.status_code == 200
        body = res.json()
        assert body["phone"] == ""
        assert body["name"] == "Test User"

    def test_missing_profile_returns_404(self, client):
        from datetime import datetime, timezone

        from app.core.security import hash_password
        from database import get_db

        db = get_db()
        doc_id = db.table("users").insert({
            "email": "noprofile@test.com",
            "hashed_password": hash_password("securepass123"),
            "is_active": True,
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db.close()
        token = create_token({"sub": str(doc_id), "role": "user"})
        res = client.get("/api/profiles/me", headers=_bearer(token))
        assert res.status_code == 404
        assert res.json()["detail"] == "Profile not found"

    def test_profile_requires_auth(self, client):
        res = client.get("/api/profiles/me")
        assert res.status_code == 401