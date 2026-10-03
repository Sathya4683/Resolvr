from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import any_user
from app.models import Notification, User
from app.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def my_notifications(db: Session = Depends(get_db), user: User = Depends(any_user)):
    #sql: SELECT * FROM notifications WHERE user_id = :user_id ORDER BY id DESC LIMIT 30
    return db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(30)
    ).all()


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(any_user)):
    #sql: UPDATE notifications SET is_read = true WHERE id = :id AND user_id = :user_id
    result = db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user.id)
        .values(is_read=True)
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(any_user)):
    #sql: UPDATE notifications SET is_read = true WHERE user_id = :user_id AND is_read = false
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
