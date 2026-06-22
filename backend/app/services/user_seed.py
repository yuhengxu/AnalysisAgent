"""用户种子数据。"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User


def ensure_default_admin(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    admin = User(
        username=settings.admin_username,
        hashed_password=hash_password(settings.admin_password),
        role="admin",
    )
    db.add(admin)
    db.commit()
