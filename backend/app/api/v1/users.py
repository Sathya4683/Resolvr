from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_only
from app.models import User
from app.schemas import UserCreate, UserOut, UserUpdate
from app.security import hash_password
from app.services import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    #sql: SELECT * FROM users ORDER BY role, username
    return db.scalars(select(User).order_by(User.role, User.username)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    #sql: SELECT id FROM users WHERE username = :username
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    user = User(
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        role=body.role,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    audit.record(db, admin, "user.create", "user", user.id, username=user.username, role=user.role)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_only)
):
    #sql: SELECT * FROM users WHERE id = :user_id
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't disable or demote your own account")

    changes = body.model_dump(exclude_unset=True)
    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if password:
        user.password_hash = hash_password(password)
        changes["password"] = "changed"

    audit.record(db, admin, "user.update", "user", user.id, changes=changes)
    db.commit()
    return user
