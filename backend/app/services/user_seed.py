"""用户种子数据。"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.report import Report
from app.models.user import User


def ensure_default_admin(db: Session) -> None:
    admin = db.query(User).filter(User.username == settings.admin_username).first()
    if not admin:
        admin = User(
            username=settings.admin_username,
            hashed_password=hash_password(settings.admin_password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    db.query(Report).filter(Report.user_id.is_(None)).update(
        {Report.user_id: admin.id}
    )
    db.commit()
