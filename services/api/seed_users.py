from datetime import datetime, timezone
from database import get_db
from app.core.security import hash_password


def seed_users():
    db = get_db()
    table = db.table("users")
    profiles_table = db.table("profiles")

    for doc in table.all():
        if doc.get("email") == "admin@trackflow.com":
            db.close()
            print("Admin user already exists. Skipping seed.")
            return

    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "email": "admin@trackflow.com",
        "hashed_password": hash_password("admin123"),
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
    print(f"Seeded admin user (id={doc_id}, email=admin@trackflow.com, password=admin123).")


if __name__ == "__main__":
    seed_users()
