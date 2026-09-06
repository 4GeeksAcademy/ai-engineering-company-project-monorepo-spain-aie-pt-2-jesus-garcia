from fastapi import APIRouter, Depends

from models import Profile, ProfileUpdate
from app.core.dependencies import get_current_user
from app.services.user_service import get_my_profile, update_my_profile

router = APIRouter(prefix="/api", tags=["profiles"])


@router.get("/profiles/me", response_model=Profile)
def read_my_profile(current_user: dict = Depends(get_current_user)):
    return get_my_profile(current_user["id"])


@router.put("/profiles/me", response_model=Profile)
def edit_my_profile(
    payload: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    return update_my_profile(current_user["id"], payload.model_dump(exclude_unset=True))