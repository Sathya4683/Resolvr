import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import any_user
from app.models import User
from app.schemas import LoginIn, LoginOut, UserOut
from app.security import create_access_token, verify_password
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger(__name__)

ROLE_NAMES = {"support_agent": "support agent", "admin": "admin", "analyst": "analyst"}


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    #sql: SELECT * FROM users WHERE username = :username
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))

    #same message for "no such user" and "wrong password" so usernames can't be guessed
    if user is None or not verify_password(body.password, user.password_hash):
        log.info("login failed", extra={"username": body.username})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")
    if body.role and user.role != body.role:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"This account doesn't have {ROLE_NAMES[body.role]} access"
        )

    user.last_login_at = datetime.now(timezone.utc)
    audit.record(db, user, "login")
    db.commit()
    request.state.username = user.username

    token = create_access_token(user.id, user.username, user.role)
    return LoginOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(any_user)):
    return user
