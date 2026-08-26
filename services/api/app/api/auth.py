import logging

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from database import get_db
from models import (
    User, UserCreate, UserUpdate, LoginRequest, TokenResponse,
    AuthMeResponse, Profile, ProfileUpdate, UserRole,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
)
from app.core.security import (
    hash_password, verify_password, create_token,
    create_password_reset_token, decode_token,
)
from app.core.dependencies import get_current_user
from app.email_service import send_password_reset_email

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    db = get_db()
    table = db.table("users")

    for doc in table.all():
        if doc.get("email") == payload.email.lower().strip():
            if not verify_password(payload.password, doc["hashed_password"]):
                db.close()
                raise HTTPException(status_code=401, detail="Invalid credentials")
            if not doc.get("is_active", True):
                db.close()
                raise HTTPException(status_code=403, detail="Account is disabled")

            user = User(
                id=str(doc.doc_id),
                email=doc["email"],
                is_active=doc["is_active"],
                role=UserRole(doc["role"]),
                created_at=doc["created_at"],
            )
            token = create_token({"sub": str(doc.doc_id), "role": doc["role"]})
            db.close()
            return TokenResponse(access_token=token, user=user)

    db.close()
    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest):
    db = get_db()
    users_table = db.table("users")

    for doc in users_table.all():
        if doc.get("email") == payload.email:
            if doc.get("is_active", True):
                token = create_password_reset_token(str(doc.doc_id))
                try:
                    send_password_reset_email(doc["email"], token)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Fallo al enviar el correo de restablecimiento"
                    )
            break

    db.close()
    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    payload_data = decode_token(payload.token)
    if payload_data is None or payload_data.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user_id = payload_data.get("sub")
    iat = payload_data.get("iat")
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    db = get_db()
    users_table = db.table("users")

    doc = None
    for d in users_table.all():
        if str(d.doc_id) == str(user_id):
            doc = d
            break

    if doc is None or not doc.get("is_active", True):
        db.close()
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
    changed_at_raw = doc.get("password_changed_at")
    if changed_at_raw:
        changed_at = datetime.fromisoformat(changed_at_raw)
        if issued_at < changed_at:
            db.close()
            raise HTTPException(status_code=400, detail="Invalid or expired token")

    users_table.update(
        {
            "hashed_password": hash_password(payload.new_password),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[doc.doc_id],
    )
    db.close()
    return {"message": "Password updated successfully"}


@router.post("/auth/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    db = get_db()
    users_table = db.table("users")
    users_table.update(
        {
            "hashed_password": hash_password(payload.new_password),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[int(current_user["id"])],
    )
    db.close()
    return {"message": "Password updated successfully"}


@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(current_user: dict = Depends(get_current_user)):
    db = get_db()
    profiles_table = db.table("profiles")
    profile = None
    for p in profiles_table.all():
        if p.get("user_id") == current_user["id"]:
            profile = Profile(
                id=str(p.doc_id),
                user_id=p["user_id"],
                name=p.get("name"),
                phone=p.get("phone"),
                address=p.get("address"),
            )
            break
    db.close()

    return AuthMeResponse(
        email=current_user["email"],
        role=UserRole(current_user["role"]),
        profile=profile or Profile(id="", user_id=current_user["id"]),
    )


@router.post("/users", response_model=User, status_code=201)
def create_user(payload: UserCreate):
    db = get_db()
    table = db.table("users")

    for doc in table.all():
        if doc.get("email") == payload.email:
            db.close()
            raise HTTPException(status_code=409, detail="Email already registered")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "email": payload.email,
        "hashed_password": hash_password(payload.password),
        "is_active": True,
        "role": UserRole.user.value,
        "created_at": now,
    }

    doc_id = table.insert(doc)

    profiles_table = db.table("profiles")
    profiles_table.insert({
        "user_id": str(doc_id),
        "name": payload.name,
        "phone": payload.phone,
        "address": payload.address,
    })

    db.close()
    return User(
        id=str(doc_id),
        email=doc["email"],
        is_active=doc["is_active"],
        role=UserRole(doc["role"]),
        created_at=doc["created_at"],
    )


@router.get("/users", response_model=list[User])
def list_users(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_db()
    table = db.table("users")
    users = []
    for doc in table.all():
        users.append(User(
            id=str(doc.doc_id),
            email=doc["email"],
            is_active=doc["is_active"],
            role=UserRole(doc["role"]),
            created_at=doc["created_at"],
        ))
    db.close()
    return users


@router.get("/users/{user_id}", response_model=User)
def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != UserRole.admin.value and current_user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    db = get_db()
    table = db.table("users")

    target_id = int(user_id) if user_id.isdigit() else user_id
    for doc in table.all():
        if doc.doc_id == target_id:
            db.close()
            return User(
                id=str(doc.doc_id),
                email=doc["email"],
                is_active=doc["is_active"],
                role=UserRole(doc["role"]),
                created_at=doc["created_at"],
            )

    db.close()
    raise HTTPException(status_code=404, detail="User not found")


@router.put("/users/{user_id}", response_model=User)
def update_user(user_id: str, payload: UserUpdate, current_user: dict = Depends(get_current_user)):
    is_admin = current_user.get("role") == UserRole.admin.value
    is_owner = current_user.get("id") == user_id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Not authorized")

    db = get_db()
    table = db.table("users")

    target_id = int(user_id) if user_id.isdigit() else user_id
    doc = None
    for d in table.all():
        if d.doc_id == target_id:
            doc = d
            break

    if doc is None:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "email" in update_data:
        for d in table.all():
            if d.doc_id != target_id and d.get("email") == update_data["email"]:
                db.close()
                raise HTTPException(status_code=409, detail="Email already in use")

    if "role" in update_data and not is_admin:
        db.close()
        raise HTTPException(status_code=403, detail="Only admins can change role")

    table.update(update_data, doc_ids=[target_id])

    for d in table.all():
        if d.doc_id == target_id:
            db.close()
            return User(
                id=str(target_id),
                email=d["email"],
                is_active=d["is_active"],
                role=UserRole(d["role"]),
                created_at=d["created_at"],
            )

    db.close()
    raise HTTPException(status_code=404, detail="User not found")


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    is_admin = current_user.get("role") == UserRole.admin.value
    is_owner = current_user.get("id") == user_id
    if not is_admin and not is_owner:
        raise HTTPException(status_code=403, detail="Not authorized")

    db = get_db()
    table = db.table("users")

    target_id = int(user_id) if user_id.isdigit() else user_id
    found = False
    for d in table.all():
        if d.doc_id == target_id:
            found = True
            break

    if not found:
        db.close()
        raise HTTPException(status_code=404, detail="User not found")

    table.remove(doc_ids=[target_id])

    profiles_table = db.table("profiles")
    for p in profiles_table.all():
        if p.get("user_id") == str(target_id):
            profiles_table.remove(doc_ids=[p.doc_id])
            break

    db.close()


@router.get("/profiles/me", response_model=Profile)
def get_my_profile(current_user: dict = Depends(get_current_user)):
    db = get_db()
    profiles_table = db.table("profiles")

    for p in profiles_table.all():
        if p.get("user_id") == current_user["id"]:
            db.close()
            return Profile(
                id=str(p.doc_id),
                user_id=p["user_id"],
                name=p.get("name"),
                phone=p.get("phone"),
                address=p.get("address"),
            )

    db.close()
    raise HTTPException(status_code=404, detail="Profile not found")


@router.put("/profiles/me", response_model=Profile)
def update_my_profile(payload: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    profiles_table = db.table("profiles")

    for p in profiles_table.all():
        if p.get("user_id") == current_user["id"]:
            update_data = payload.model_dump(exclude_unset=True)
            if update_data:
                profiles_table.update(update_data, doc_ids=[p.doc_id])
            for updated in profiles_table.all():
                if updated.doc_id == p.doc_id:
                    db.close()
                    return Profile(
                        id=str(updated.doc_id),
                        user_id=updated["user_id"],
                        name=updated.get("name"),
                        phone=updated.get("phone"),
                        address=updated.get("address"),
                    )

    db.close()
    raise HTTPException(status_code=404, detail="Profile not found")
