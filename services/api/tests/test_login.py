from app.core.security import decode_token


class TestLogin:
    def test_valid_credentials_return_signed_token(self, client, register_user):
        payload, _ = register_user
        res = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"],
        })
        assert res.status_code == 200
        body = res.json()
        assert body["token_type"] == "bearer"
        assert "access_token" in body
        claims = decode_token(body["access_token"])
        assert claims["sub"] == body["user"]["id"]
        assert body["user"]["email"] == payload["email"]
        assert body["user"]["role"] == "user"

    def test_login_is_case_insensitive_on_email(self, client, register_user):
        payload, _ = register_user
        res = client.post("/api/auth/login", json={
            "email": payload["email"].upper(),
            "password": payload["password"],
        })
        assert res.status_code == 200

    def test_wrong_password_returns_401_without_token(self, client, register_user):
        payload, _ = register_user
        res = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": "wrong-password",
        })
        assert res.status_code == 401
        assert "access_token" not in res.json()

    def test_unknown_email_returns_same_401(self, client):
        res = client.post("/api/auth/login", json={
            "email": "ghost@test.com",
            "password": "whatever123",
        })
        assert res.status_code == 401
        assert "access_token" not in res.json()

    def test_inactive_user_is_rejected_with_403(self, client, register_user):
        payload, created = register_user
        user_id = created.json()["id"]
        from database import get_tinydb
        db = get_tinydb()
        db.table("users").update({"is_active": False}, doc_ids=[int(user_id)])
        db.close()
        res = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"],
        })
        assert res.status_code == 403
        assert res.json()["detail"] == "Account is disabled"


class TestPasswordFlows:
    def test_change_password_with_valid_current(self, client, user_headers, register_user):
        payload, _ = register_user
        res = client.post("/api/auth/change-password", headers=user_headers, json={
            "current_password": payload["password"],
            "new_password": "new-secure-pass",
        })
        assert res.status_code == 200
        old_login = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"],
        })
        assert old_login.status_code == 401
        new_login = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": "new-secure-pass",
        })
        assert new_login.status_code == 200

    def test_change_password_with_wrong_current_returns_400(self, client, user_headers):
        res = client.post("/api/auth/change-password", headers=user_headers, json={
            "current_password": "not-the-password",
            "new_password": "new-secure-pass",
        })
        assert res.status_code == 400
        assert res.json()["detail"] == "Current password is incorrect"

    def test_change_password_requires_auth(self, client):
        res = client.post("/api/auth/change-password", json={
            "current_password": "x",
            "new_password": "abcdef",
        })
        assert res.status_code == 401

    def test_reset_password_with_valid_token(self, client, register_user):
        payload, created = register_user
        from app.core.security import create_password_reset_token
        token = create_password_reset_token(created.json()["id"])
        res = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "reset-pass-123",
        })
        assert res.status_code == 200
        login = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": "reset-pass-123",
        })
        assert login.status_code == 200

    def test_reset_password_rejects_tampered_token(self, client):
        res = client.post("/api/auth/reset-password", json={
            "token": "not-a-real-token",
            "new_password": "reset-pass-123",
        })
        assert res.status_code == 400
        assert res.json()["detail"] == "Invalid or expired token"

    def test_old_reset_token_invalidated_after_password_change(self, client, register_user, user_headers):
        payload, created = register_user
        from app.core.security import create_password_reset_token
        old_token = create_password_reset_token(created.json()["id"])
        change = client.post("/api/auth/change-password", headers=user_headers, json={
            "current_password": payload["password"],
            "new_password": "rotated-pass-1",
        })
        assert change.status_code == 200
        res = client.post("/api/auth/reset-password", json={
            "token": old_token,
            "new_password": "should-fail-1",
        })
        assert res.status_code == 400

    def test_forgot_password_returns_generic_message_for_unknown_email(self, client):
        res = client.post("/api/auth/forgot-password", json={"email": "ghost@test.com"})
        assert res.status_code == 202
        assert res.json()["message"] == "If the email exists, a reset link has been sent"

    def test_forgot_password_issues_token_for_existing_user(self, client, register_user, monkeypatch):
        payload, _ = register_user
        sent = {}
        import app.routes.auth as auth_route
        monkeypatch.setattr(
            auth_route,
            "send_password_reset_email",
            lambda email, token: sent.update({"email": email, "token": token}),
        )
        res = client.post("/api/auth/forgot-password", json={"email": payload["email"]})
        assert res.status_code == 202
        assert sent["email"] == payload["email"]
        assert sent["token"]

    def test_forgot_password_inactive_user_gets_no_token(self, client, register_user, monkeypatch):
        payload, created = register_user
        from database import get_tinydb
        db = get_tinydb()
        db.table("users").update({"is_active": False}, doc_ids=[int(created.json()["id"])])
        db.close()
        sent = {}
        import app.routes.auth as auth_route
        monkeypatch.setattr(
            auth_route,
            "send_password_reset_email",
            lambda email, token: sent.update({"email": email, "token": token}),
        )
        res = client.post("/api/auth/forgot-password", json={"email": payload["email"]})
        assert res.status_code == 202
        assert sent == {}

    def test_reset_password_rejects_token_for_unknown_user(self, client):
        from app.core.security import create_password_reset_token
        token = create_password_reset_token("99999")
        res = client.post("/api/auth/reset-password", json={
            "token": token,
            "new_password": "whatever123",
        })
        assert res.status_code == 400