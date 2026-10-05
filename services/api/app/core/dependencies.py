from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import get_tinydb

from ..core.security import decode_token
from ..core.cache import cache
from models import UserRole

security_scheme = HTTPBearer()

AUTH_TTL = 5  # segundos
AUTH_PREFIX = "auth:"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
):
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    key = f"{AUTH_PREFIX}user:{user_id}"
    hit = cache.get(key)
    if hit is not None:
        return hit

    db = get_tinydb()
    table = db.table("users")
    for doc in table.all():
        if str(doc.doc_id) == str(user_id):
            db.close()
            user = {
                "id": str(doc.doc_id),
                "email": doc.get("email"),
                "is_active": doc.get("is_active", True),
                "role": doc.get("role", "user"),
                "created_at": doc.get("created_at"),
            }
            cache.set(key, user, ttl=AUTH_TTL)
            return user

    db.close()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found",
    )


def invalidate_user_cache(user_id: str) -> None:
    cache.delete(f"{AUTH_PREFIX}user:{user_id}")


def require_role(min_role: UserRole):
    def checker(current_user: dict = Depends(get_current_user)):
        role_value = UserRole(current_user.get("role", "user"))
        role_order = [UserRole.user, UserRole.manager, UserRole.admin]
        if role_order.index(role_value) < role_order.index(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return checker


require_manager = require_role(UserRole.manager)
require_admin = require_role(UserRole.admin)
