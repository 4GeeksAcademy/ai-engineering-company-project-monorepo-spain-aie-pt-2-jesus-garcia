import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from models import (
    AuthMeResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.core.security import create_token, decode_token
from app.core.dependencies import get_current_user
from app.email_service import send_password_reset_email
from app.services.user_service import (
    apply_password_reset,
    authenticate,
    build_auth_me,
    change_password,
    issue_password_reset_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    user = authenticate(payload.email, payload.password)
    token = create_token({"sub": user.id, "role": user.role.value})
    return TokenResponse(access_token=token, user=user)


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(payload: ForgotPasswordRequest):
    token = issue_password_reset_token(payload.email)
    if token is not None:
        try:
            send_password_reset_email(payload.email, token)
        except Exception:  # noqa: BLE001
            logger.exception("Fallo al enviar el correo de restablecimiento")
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

    issued_at = datetime.fromtimestamp(iat, tz=timezone.utc)
    apply_password_reset(user_id, payload.new_password, issued_at)
    return {"message": "Password updated successfully"}


@router.post("/auth/change-password")
def change_password_route(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    change_password(current_user["id"], payload.current_password, payload.new_password)
    return {"message": "Password updated successfully"}


@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(current_user: dict = Depends(get_current_user)):
    return build_auth_me(current_user["id"], current_user)