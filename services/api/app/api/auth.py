from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone

from database import get_db
from models import (
    User, UserCreate, UserUpdate, LoginRequest, TokenResponse,
    Profile, ProfileUpdate, UserRole,
)
from app.core.security import hash_password, verify_password, create_token
from app.core.dependencies import get_current_user

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
