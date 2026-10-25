import pytest


def _register(client, email="c6@test.com"):
    res = client.post(
        "/api/users",
        json={"email": email, "password": "securepass123", "name": "C6"},
    )
    assert res.status_code == 201
    return res.json()


def _login(client, email="c6@test.com"):
    res = client.post(
        "/api/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


class TestAuthCache:
    def test_current_user_is_cached_across_requests(self, client, auth_headers):
        from app.core.cache import cache

        user = _register(client)
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 200
        key = f"auth:user:{user['id']}"
        assert cache.get(key) is not None
        assert client.get("/api/auth/me", headers=headers).status_code == 200

    def test_role_change_invalidates_auth_cache(self, client, auth_headers):
        from app.core.cache import cache

        user = _register(client)
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        res = client.get("/api/suppliers", headers=headers)
        assert res.status_code == 403
        key = f"auth:user:{user['id']}"
        assert cache.get(key) is not None
        assert cache.get(key)["role"] == "user"

        res = client.put(
            f"/api/users/{user['id']}",
            headers=auth_headers,
            json={"role": "manager"},
        )
        assert res.status_code == 200
        assert cache.get(key) is None

        res = client.get("/api/suppliers", headers=headers)
        assert res.status_code == 200

    def test_delete_user_invalidates_auth_cache(self, client, auth_headers):
        from app.core.cache import cache

        user = _register(client)
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        client.get("/api/auth/me", headers=headers)
        key = f"auth:user:{user['id']}"
        assert cache.get(key) is not None

        res = client.delete(f"/api/users/{user['id']}", headers=auth_headers)
        assert res.status_code == 204
        assert cache.get(key) is None

    def test_deleted_user_is_rejected_after_cache_clear(self, client, auth_headers):
        from app.core.cache import cache

        user = _register(client)
        token = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        client.get("/api/auth/me", headers=headers)
        client.delete(f"/api/users/{user['id']}", headers=auth_headers)
        key = f"auth:user:{user['id']}"
        assert cache.get(key) is None

        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 401