from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(
    db: Session,
    user: User | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    **details,
) -> None:
    """adds an audit row to the current transaction, it is saved together with the change itself"""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
        )
    )
