from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import get_tinydb

from ..core.security import decode_token
from models import UserRole

security_scheme = HTTPBearer()


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

    db = get_tinydb()
    table = db.table("users")
    for doc in table.all():
        if str(doc.doc_id) == str(user_id):
            db.close()
            return {"id": str(doc.doc_id), **doc}

    db.close()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not found",
    )


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
