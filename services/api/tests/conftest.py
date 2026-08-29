import io
import os
import sys
from pathlib import Path

os.environ["SECRET_KEY"] = os.environ.get("SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import create_app  # noqa: E402
from app.core.security import hash_password, create_token  # noqa: E402

SAMPLE_CSV = """customer_id,first_name,last_name,email,phone,department,status,category,satisfaction_score,created_at
CUST-1000,María,García,maria.garcia@empresa.es,+34 614 126225,Experiencia del cliente,descartado,consulta_general,,2025-03-04
CUST-1001,Juan,López,juan.lopez@hotmail.com,+34 617 872246,Experiencia del cliente,abierto,seguimiento,,2025-06-01
CUST-1002,Ana,Martínez,ana.martinez@yahoo.es,+34 604 131244,Experiencia del cliente,cerrado,devolución,8,2025-03-01
CUST-1003,Luis,Rodríguez,luis.rodriguez@trackflow.com,+34 677 127824,Experiencia del cliente,cerrado,incidencia,9,2025-06-16
CUST-1004,Carmen,Sánchez,carmen.sanchez@empresa.es,+34 669 539898,Experiencia del cliente,abierto,incidencia,,2025-05-31
"""

EMPTY_CSV = ""

INVALID_HEADER_CSV = """foo,bar,baz
1,2,3
"""


@pytest.fixture(autouse=True)
def _clean_db():
    from database import get_db
    db = get_db()
    for table_name in ("users", "profiles", "incidents"):
        db.table(table_name).truncate()

    users = db.table("users")
    from datetime import datetime, timezone
    users.insert({
        "email": "admin@test.com",
        "hashed_password": hash_password("admin123"),
        "is_active": True,
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    db.close()


@pytest.fixture()
def admin_token():
    return create_token({"sub": "1", "role": "admin"})


@pytest.fixture()
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def register_user(client):
    payload = {
        "email": "user@test.com",
        "password": "securepass123",
        "name": "Test User",
        "phone": "+34 600 000000",
        "address": "Calle Test 1",
    }
    created = client.post("/api/users", json=payload)
    return payload, created


@pytest.fixture()
def user_token(client, register_user):
    payload, _ = register_user
    login = client.post("/api/auth/login", json={
        "email": payload["email"],
        "password": payload["password"],
    })
    return login.json()["access_token"]


@pytest.fixture()
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture(autouse=True)
def _reset_service_state():
    from app.incidents import service

    service.reset()
    yield
    service.reset()


@pytest.fixture()
def sample_csv_bytes() -> bytes:
    return SAMPLE_CSV.encode("utf-8")


@pytest.fixture()
def empty_csv_bytes() -> bytes:
    return EMPTY_CSV.encode("utf-8")


@pytest.fixture()
def invalid_header_csv_bytes() -> bytes:
    return INVALID_HEADER_CSV.encode("utf-8")


def upload(client, content: bytes, headers: dict, filename: str = "COMPANY.csv"):
    return client.post(
        "/api/incidents/analyze",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
        headers=headers,
    )