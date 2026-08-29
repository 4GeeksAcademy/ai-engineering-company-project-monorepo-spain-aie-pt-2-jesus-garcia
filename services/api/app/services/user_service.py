from datetime import datetime, timezone

from fastapi import HTTPException

from database import get_db
from models import (
    AuthMeResponse,
    Profile,
    ProfileUpdate,
    User,
    UserRole,
)
from app.core.security import create_password_reset_token, hash_password, verify_password


def _find_doc(table, user_id):
    target_id = int(user_id) if user_id.isdigit() else user_id
    for doc in table.all():
        if doc.doc_id == target_id:
            return doc
    return None


def _user_from_doc(doc) -> User:
    return User(
        id=str(doc.doc_id),
        email=doc["email"],
        is_active=doc["is_active"],
        role=UserRole(doc["role"]),
        created_at=doc["created_at"],
    )


def _profile_from_doc(doc) -> Profile:
    return Profile(
        id=str(doc.doc_id),
        user_id=doc["user_id"],
        name=doc.get("name"),
        phone=doc.get("phone"),
        address=doc.get("address"),
    )


def find_profile_for_user(profiles_table, user_id):
    for p in profiles_table.all():
        if p.get("user_id") == user_id:
            return p
    return None


def register_user(email: str, password: str, name, phone, address) -> User:
    db = get_db()
    table = db.table("users")

    for doc in table.all():
        if doc.get("email") == email:
            db.close()
            raise HTTPException(status_code=409, detail="Email already registered")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "email": email,
        "hashed_password": hash_password(password),
        "is_active": True,
        "role": UserRole.user.value,
        "created_at": now,
    }

    doc_id = table.insert(doc)

    profiles_table = db.table("profiles")
    profiles_table.insert({
        "user_id": str(doc_id),
        "name": name,
        "phone": phone,
        "address": address,
    })

    db.close()
    return User(
        id=str(doc_id),
        email=doc["email"],
        is_active=True,
        role=UserRole.user,
        created_at=now,
    )


def authenticate(email: str, password: str) -> User:
    db = get_db()
    table = db.table("users")

    for doc in table.all():
        if doc.get("email") == email.lower().strip():
            if not verify_password(password, doc["hashed_password"]):
                db.close()
                raise HTTPException(status_code=401, detail="Invalid credentials")
            if not doc.get("is_active", True):
                db.close()
                raise HTTPException(status_code=403, detail="Account is disabled")

            user = _user_from_doc(doc)
            db.close()
            return user

    db.close()
    raise HTTPException(status_code=401, detail="Invalid credentials")


def list_users() -> list[User]:
    db = get_db()
    table = db.table("users")
    users = [_user_from_doc(doc) for doc in table.all()]
    db.close()
    return users


def get_user(user_id: str) -> User:
    db = get_db()
    table = db.table("users")
    doc = _find_doc(table, user_id)
    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")
    user = _user_from_doc(doc)
    db.close()
    return user


def update_user(user_id: str, update_data: dict, current_user: dict) -> User:
    is_admin = current_user.get("role") == UserRole.admin.value
    is_owner = current_user.get("id") == user_id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Not authorized")

    db = get_db()
    table = db.table("users")

    doc = _find_doc(table, user_id)
    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    if "email" in update_data:
        for d in table.all():
            if d.doc_id != doc.doc_id and d.get("email") == update_data["email"]:
                db.close()
                raise HTTPException(status_code=409, detail="Email already in use")

    if "role" in update_data and not is_admin:
        db.close()
        raise HTTPException(status_code=403, detail="Only admins can change role")

    table.update(update_data, doc_ids=[doc.doc_id])

    for d in table.all():
        if d.doc_id == doc.doc_id:
            user = _user_from_doc(d)
            db.close()
            return user

    db.close()
    raise HTTPException(status_code=404, detail="User not found")


def delete_user(user_id: str, current_user: dict) -> None:
    is_admin = current_user.get("role") == UserRole.admin.value
    is_owner = current_user.get("id") == user_id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Not authorized")

    db = get_db()
    table = db.table("users")

    doc = _find_doc(table, user_id)
    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    table.remove(doc_ids=[doc.doc_id])

    profiles_table = db.table("profiles")
    profile = find_profile_for_user(profiles_table, user_id)
    if profile is not None:
        profiles_table.remove(doc_ids=[profile.doc_id])

    db.close()


def build_auth_me(user_id: str, current_user: dict) -> AuthMeResponse:
    profile = get_profile_for_user(user_id)
    return AuthMeResponse(
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        profile=profile or Profile(id="", user_id=user_id),
    )


def get_profile_for_user(user_id: str) -> Profile | None:
    db = get_db()
    profiles_table = db.table("profiles")
    profile = find_profile_for_user(profiles_table, user_id)
    if profile is None:
        db.close()
        return None
    result = _profile_from_doc(profile)
    db.close()
    return result


def get_my_profile(user_id: str) -> Profile:
    db = get_db()
    profiles_table = db.table("profiles")
    profile = find_profile_for_user(profiles_table, user_id)
    if profile is None:
        db.close()
        raise HTTPException(status_code=404, detail="Profile not found")
    result = _profile_from_doc(profile)
    db.close()
    return result


def update_my_profile(user_id: str, update_data: dict) -> Profile:
    db = get_db()
    profiles_table = db.table("profiles")

    profile = find_profile_for_user(profiles_table, user_id)
    if profile is None:
        db.close()
        raise HTTPException(status_code=404, detail="Profile not found")

    if update_data:
        profiles_table.update(update_data, doc_ids=[profile.doc_id])

    for updated in profiles_table.all():
        if updated.doc_id == profile.doc_id:
            result = _profile_from_doc(updated)
            db.close()
            return result

    db.close()
    raise HTTPException(status_code=404, detail="Profile not found")


def change_password(user_id: str, current_password: str, new_password: str) -> None:
    db = get_db()
    table = db.table("users")

    doc = _find_doc(table, user_id)
    if doc is None or not verify_password(current_password, doc.get("hashed_password", "")):
        db.close()
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    table.update(
        {
            "hashed_password": hash_password(new_password),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[doc.doc_id],
    )
    db.close()


def apply_password_reset(user_id: str, new_password: str, token_iat) -> None:
    db = get_db()
    table = db.table("users")

    doc = _find_doc(table, user_id)
    if doc is None or not doc.get("is_active", True):
        db.close()
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    changed_at_raw = doc.get("password_changed_at")
    if changed_at_raw and token_iat is not None:
        try:
            changed_at = datetime.fromisoformat(changed_at_raw)
        except ValueError:
            db.close()
            raise HTTPException(status_code=400, detail="Invalid or expired token")
        if token_iat < changed_at:
            db.close()
            raise HTTPException(status_code=400, detail="Invalid or expired token")

    table.update(
        {
            "hashed_password": hash_password(new_password),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[doc.doc_id],
    )
    db.close()


def issue_password_reset_token(email: str) -> str | None:
    db = get_db()
    users_table = db.table("users")

    for doc in users_table.all():
        if doc.get("email") == email:
            if doc.get("is_active", True):
                token = create_password_reset_token(str(doc.doc_id))
                db.close()
                return token
            break

    db.close()
    return None