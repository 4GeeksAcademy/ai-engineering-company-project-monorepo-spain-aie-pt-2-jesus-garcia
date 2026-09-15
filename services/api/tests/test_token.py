from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.security import ALGORITHM, SECRET_KEY


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


class TestToken:
    def test_valid_token_identifies_user(self, client, user_token, register_user):
        payload, _ = register_user
        me = client.get("/api/auth/me", headers=_bearer(user_token))
        assert me.status_code == 200
        body = me.json()
        assert body["email"] == payload["email"]
        assert body["role"] == "user"
        assert body["profile"]["name"] == "Test User"

    def test_token_near_expiry_is_still_valid(self, client):
        token = jwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        me = client.get("/api/auth/me", headers=_bearer(token))
        assert me.status_code == 200

    def test_expired_token_returns_401(self, client):
        token = jwt.encode(
            {
                "sub": "1",
                "role": "admin",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        me = client.get("/api/auth/me", headers=_bearer(token))
        assert me.status_code == 401
        assert "email" not in me.json()

    def test_malformed_token_returns_401(self, client):
        me = client.get("/api/auth/me", headers=_bearer("not-a-jwt"))
        assert me.status_code == 401

    def test_token_from_unknown_user_returns_401(self, client):
        token = jwt.encode(
            {
                "sub": "99999",
                "role": "admin",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        me = client.get("/api/auth/me", headers=_bearer(token))
        assert me.status_code == 401
        assert me.json()["detail"] == "User not found"

    def test_missing_header_returns_401(self, client):
        me = client.get("/api/auth/me")
        assert me.status_code == 401