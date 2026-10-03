import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again") from None

    #sql: SELECT * FROM users WHERE id = :id
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or disabled")

    #picked up by the request logging middleware
    request.state.username = user.username
    return user


def require_roles(*roles: str):
    """dependency factory: Depends(require_roles("admin")) only lets admins through"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission to do this")
        return user

    return checker


#shortcuts used across the routers
any_user = get_current_user
admin_only = require_roles("admin")
agent_or_admin = require_roles("support_agent", "admin")
analyst_or_admin = require_roles("analyst", "admin")
