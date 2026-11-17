"""Crea el usuario admin de desarrollo.

La contraseña no está en el código: se lee de ``SEED_ADMIN_PASSWORD`` o se
genera aleatoriamente y se imprime una sola vez. En producción la cuenta se
crea por el procedimiento operativo, nunca con este script.
"""

from datetime import datetime, timezone
import os
import secrets
import sys

from database import get_tinydb
from app.core.security import hash_password

ADMIN_EMAIL = "admin@trackflow.com"


def resolve_admin_password() -> str:
    configured = (os.getenv("SEED_ADMIN_PASSWORD") or "").strip()
    if configured:
        return configured
    return secrets.token_urlsafe(12)


def seed_users():
    db = get_tinydb()
    table = db.table("users")
    profiles_table = db.table("profiles")

    for doc in table.all():
        if doc.get("email") == ADMIN_EMAIL:
            db.close()
            print("Admin user already exists. Skipping seed.")
            return

    password = resolve_admin_password()
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "email": ADMIN_EMAIL,
        "hashed_password": hash_password(password),
        "is_active": True,
        "role": "admin",
        "created_at": now,
    }

    doc_id = table.insert(user_doc)

    profiles_table.insert({
        "user_id": str(doc_id),
        "name": "Admin",
        "phone": None,
        "address": None,
    })

    db.close()
    print(
        f"Seeded admin user (id={doc_id}, email={ADMIN_EMAIL}, "
        f"password={password})."
    )
    if not (os.getenv("SEED_ADMIN_PASSWORD") or "").strip():
        print(
            "Contraseña generada: guárdala ahora, no se vuelve a mostrar. "
            "Para fijarla, define SEED_ADMIN_PASSWORD."
        )


def main():
    try:
        seed_users()
    except Exception as exc:  # noqa: BLE001
        print(f"Error al seedear el usuario admin: {exc}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
