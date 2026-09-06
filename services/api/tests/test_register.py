class TestRegister:
    def test_valid_credentials_create_user_with_role_user(self, client, register_user):
        payload, created = register_user
        assert created.status_code == 201
        body = created.json()
        assert body["email"] == payload["email"]
        assert body["role"] == "user"
        assert body["is_active"] is True
        assert "id" in body
        assert "created_at" in body
        assert "password" not in body
        assert "hashed_password" not in body

    def test_register_creates_linked_profile(self, client, register_user):
        payload, created = register_user
        user_id = created.json()["id"]
        login = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"],
        })
        token = login.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["profile"]["name"] == "Test User"
        assert me.json()["profile"]["user_id"] == user_id

    def test_duplicate_email_is_rejected(self, client, admin_token, register_user):
        payload, first = register_user
        assert first.status_code == 201
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        users_before = client.get("/api/users", headers=admin_headers).json()

        second = client.post("/api/users", json=payload)
        assert second.status_code == 409
        assert second.json()["detail"] == "Email already registered"

        users_after = client.get("/api/users", headers=admin_headers).json()
        assert len(users_after) == len(users_before)

    def test_invalid_email_format_returns_422_without_writing(self, client, admin_token):
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        before = len(client.get("/api/users", headers=admin_headers).json())
        res = client.post("/api/users", json={
            "email": "not-an-email",
            "password": "securepass123",
        })
        assert res.status_code == 422
        after = len(client.get("/api/users", headers=admin_headers).json())
        assert after == before

    def test_short_password_returns_422(self, client):
        res = client.post("/api/users", json={
            "email": "shortpw@test.com",
            "password": "123",
        })
        assert res.status_code == 422

    def test_every_new_user_gets_role_user_even_with_privileged_fields(self, client):
        res = client.post("/api/users", json={
            "email": "sneaky@test.com",
            "password": "securepass123",
            "name": "Sneaky",
        })
        assert res.status_code == 201
        assert res.json()["role"] == "user"


class TestUserCrud:
    def _register_second(self, client, email="second@test.com"):
        res = client.post("/api/users", json={
            "email": email,
            "password": "securepass123",
            "name": "Second User",
        })
        assert res.status_code == 201
        return res.json()

    def test_owner_can_get_own_user(self, client, user_headers, register_user):
        payload, created = register_user
        res = client.get(f"/api/users/{created.json()['id']}", headers=user_headers)
        assert res.status_code == 200
        assert res.json()["email"] == payload["email"]

    def test_non_owner_cannot_get_other_user(self, client, user_headers, register_user):
        _, created = register_user
        other = self._register_second(client)
        res = client.get(f"/api/users/{other['id']}", headers=user_headers)
        assert res.status_code == 403

    def test_non_admin_cannot_list_users(self, client, user_headers):
        res = client.get("/api/users", headers=user_headers)
        assert res.status_code == 403

    def test_admin_can_list_users(self, client, admin_token, register_user):
        headers = {"Authorization": f"Bearer {admin_token}"}
        res = client.get("/api/users", headers=headers)
        assert res.status_code == 200
        emails = [user["email"] for user in res.json()]
        assert "admin@test.com" in emails
        assert "user@test.com" in emails

    def test_owner_can_update_own_email(self, client, user_headers, register_user):
        _, created = register_user
        res = client.put(
            f"/api/users/{created.json()['id']}",
            headers=user_headers,
            json={"email": "updated@test.com"},
        )
        assert res.status_code == 200
        assert res.json()["email"] == "updated@test.com"

    def test_user_cannot_change_role(self, client, user_headers, register_user):
        _, created = register_user
        res = client.put(
            f"/api/users/{created.json()['id']}",
            headers=user_headers,
            json={"role": "manager"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "Only admins can change role"

    def test_non_owner_cannot_update_other_user(self, client, user_headers, register_user):
        _, created = register_user
        other = self._register_second(client)
        res = client.put(
            f"/api/users/{other['id']}",
            headers=user_headers,
            json={"email": "hack@test.com"},
        )
        assert res.status_code == 403

    def test_admin_can_change_role(self, client, admin_token, register_user):
        _, created = register_user
        res = client.put(
            f"/api/users/{created.json()['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "manager"},
        )
        assert res.status_code == 200
        assert res.json()["role"] == "manager"

    def test_update_unknown_user_returns_404(self, client, admin_token):
        res = client.put(
            "/api/users/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"email": "x@test.com"},
        )
        assert res.status_code == 404

    def test_update_with_duplicate_email_returns_409(self, client, user_headers, register_user):
        _, created = register_user
        other = self._register_second(client)
        res = client.put(
            f"/api/users/{created.json()['id']}",
            headers=user_headers,
            json={"email": other["email"]},
        )
        assert res.status_code == 409

    def test_owner_can_delete_own_account(self, client, user_headers, register_user):
        payload, created = register_user
        res = client.delete(f"/api/users/{created.json()['id']}", headers=user_headers)
        assert res.status_code == 204
        login = client.post("/api/auth/login", json={
            "email": payload["email"],
            "password": payload["password"],
        })
        assert login.status_code == 401

    def test_delete_unknown_user_returns_404(self, client, admin_token):
        res = client.delete(
            "/api/users/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 404

    def test_non_owner_cannot_delete_other_user(self, client, user_headers, register_user):
        _, created = register_user
        other = self._register_second(client)
        res = client.delete(f"/api/users/{other['id']}", headers=user_headers)
        assert res.status_code == 403