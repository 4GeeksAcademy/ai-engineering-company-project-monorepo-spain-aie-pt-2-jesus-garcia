#!/usr/bin/env python3
"""Matriz reproducible de control de acceso (antes/después).

Arranca la API con una base de datos temporal, siembra un usuario de cada rol
(admin, manager, user) y muestra el código HTTP de los endpoints sensibles para
cada rol. No toca la base de datos del proyecto ni requiere el stack Docker.

Uso:
    cd services/api
    source venv/bin/activate
    python ../../scripts/security/authz_matrix.py

Salida: Markdown por stdout (redirigible a docs/cybersecurity/evidence/*).
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "services" / "api"

sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(REPO_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="trackflow-authz-"))
os.environ.setdefault("SECRET_KEY", "authz-matrix-secret-key-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP / 'authz.db'}")
os.environ.setdefault("REALTIME_BROKER", "local")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("RATE_LIMIT_ENABLED", "0")
os.environ.setdefault("AGENT_MEMORY_ENABLED", "0")

import database  # noqa: E402

database.DB_DIR = str(_TMP)
database.DB_PATH = str(_TMP / "suppliers.json")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import create_token, hash_password  # noqa: E402
from app.main import create_app  # noqa: E402

ROLES = ("admin", "manager", "user")
TOKENS: dict[str, str] = {}


def _seed_users() -> None:
    db = database.get_tinydb()
    users = db.table("users")
    users.truncate()
    for index, role in enumerate(ROLES, start=1):
        users.insert(
            {
                "email": f"{role}@authz.test",
                "hashed_password": hash_password("authz-password-123"),
                "is_active": True,
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        # El id de TinyDB es 1, 2, 3 en el orden de inserción.
        TOKENS[role] = create_token({"sub": str(index), "role": role})
    db.close()


def _headers(role: str | None) -> dict[str, str]:
    if role is None:
        return {}
    return {"Authorization": f"Bearer {TOKENS[role]}"}


def _status(client: TestClient, method: str, path: str, role: str | None, **kwargs) -> int:
    response = client.request(method, path, headers=_headers(role), **kwargs)
    return response.status_code


def main() -> int:
    _seed_users()
    app = create_app()
    rows: list[tuple[str, str, str, str]] = []
    with TestClient(app) as client:
        checks = [
            ("GET", "/telemetry/report", None, {}),
            ("GET", "/telemetry/report", "user", {}),
            ("GET", "/telemetry/report", "manager", {}),
            ("GET", "/inventory/products", None, {}),
            ("GET", "/inventory/products", "user", {}),
            ("GET", "/inventory/products", "manager", {}),
            ("GET", "/agent/memory", None, {}),
            ("GET", "/agent/memory", "user", {}),
            ("GET", "/agent/memory", "manager", {}),
            ("POST", "/knowledge/query", "user", {"json": {"question": "¿SLA estándar?"}}),
            ("POST", "/knowledge/query", "manager", {"json": {"question": "¿SLA estándar?"}}),
            ("POST", "/api/users", None, {"json": {
                "email": "self-registered@authz.test",
                "password": "self-registered-123",
            }}),
            ("POST", "/chat/sessions", "user", {"json": {"client_id": "otra-marca"}}),
            ("POST", "/chat/sessions", "manager", {"json": {"client_id": "otra-marca"}}),
        ]
        for method, path, role, kwargs in checks:
            try:
                status = _status(client, method, path, role, **kwargs)
            except Exception as exc:  # noqa: BLE001 - la matriz no debe romperse
                status = f"ERROR:{type(exc).__name__}"
            rows.append((method, path, role or "anonymous", str(status)))

    print("| Método | Endpoint | Rol | HTTP |")
    print("|---|---|---|---|")
    for method, path, role, status in rows:
        print(f"| {method} | `{path}` | {role} | {status} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
