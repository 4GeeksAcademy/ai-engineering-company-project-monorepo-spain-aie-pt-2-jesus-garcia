from fastapi import APIRouter, Depends, HTTPException

from models import User, UserCreate, UserRole, UserUpdate
from app.core.dependencies import get_current_user
from app.services.user_service import (
    delete_user,
    get_user,
    list_users,
    register_user,
    update_user,
)

router = APIRouter(prefix="/api", tags=["users"])


@router.post("/users", response_model=User, status_code=201)
def create_user_account(payload: UserCreate):
    return register_user(
        payload.email,
        payload.password,
        payload.name,
        payload.phone,
        payload.address,
    )


@router.get("/users", response_model=list[User])
def list_all_users(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="Admin access required")
    return list_users()


@router.get("/users/{user_id}", response_model=User)
def get_user_by_id(user_id: str, current_user: dict = Depends(get_current_user)):
    is_admin = current_user.get("role") == UserRole.admin.value
    if not is_admin and current_user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return get_user(user_id)


@router.put("/users/{user_id}", response_model=User)
def update_user_account(
    user_id: str,
    payload: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    return update_user(user_id, payload.model_dump(exclude_unset=True), current_user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user_account(user_id: str, current_user: dict = Depends(get_current_user)):
    delete_user(user_id, current_user)