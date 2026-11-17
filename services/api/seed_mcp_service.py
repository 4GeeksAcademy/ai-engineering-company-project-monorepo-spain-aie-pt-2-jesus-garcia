from datetime import datetime, timezone
import os
import sys

from database import get_tinydb
from app.core.security import hash_password, verify_password

DEFAULT_EMAIL = "mcp-service@trackflow.com"
MANAGED_ROLES = ("admin", "manager")


def seed_mcp_service():
    email = os.getenv("MCP_SERVICE_EMAIL", DEFAULT_EMAIL).strip().lower()
    password = os.getenv("MCP_SERVICE_PASSWORD")
    name = os.getenv("MCP_SERVICE_NAME", "MCP Service")

    if not password:
        print("MCP_SERVICE_PASSWORD is required (set it in the environment).")
        sys.exit(2)

    db = get_tinydb()
    users = db.table("users")
    profiles = db.table("profiles")

    try:
        existing = next((doc for doc in users.all() if doc.get("email") == email), None)

        if existing is None:
            user_id = str(
                users.insert(
                    {
                        "email": email,
                        "hashed_password": hash_password(password),
                        "is_active": True,
                        "role": "manager",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            )
            action = "created"
        else:
            user_id = str(existing.doc_id)
            updates = {"is_active": True}
            if existing.get("role") not in MANAGED_ROLES:
                updates["role"] = "manager"
            if not verify_password(password, existing["hashed_password"]):
                updates["hashed_password"] = hash_password(password)
            users.update(updates, doc_ids=[existing.doc_id])
            action = "updated"

        profile = next(
            (doc for doc in profiles.all() if doc.get("user_id") == user_id), None
        )
        if profile is None:
            profiles.insert(
                {
                    "user_id": user_id,
                    "name": name,
                    "phone": None,
                    "address": None,
                }
            )
    finally:
        db.close()

    print(f"MCP service account {action}: {email} (id={user_id}, role=manager).")


def main():
    try:
        seed_mcp_service()
    except Exception as exc:  # noqa: BLE001
        print(f"Error seeding MCP service account: {exc}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
