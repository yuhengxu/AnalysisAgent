import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models.user import ALL_PAGE_KEYS, PAGE_LABELS, User

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_admin)],
)


class UserCreateRequest(BaseModel):
    username: str
    allowed_pages: list[str] = []


class UserUpdateRequest(BaseModel):
    allowed_pages: list[str] | None = None
    is_active: bool | None = None


def validate_allowed_pages(pages: list[str]) -> list[str]:
    valid = set(ALL_PAGE_KEYS)
    return [p for p in pages if p in valid]


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "allowed_pages": user.business_allowed_pages() if user.role != "admin" else user.allowed_pages(),
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.get("/page-options")
def get_page_options():
    return [{"key": k, "label": PAGE_LABELS[k]} for k in ALL_PAGE_KEYS]


@router.get("")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [serialize_user(u) for u in users]


@router.post("")
def create_user(body: UserCreateRequest, db: Session = Depends(get_db)):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")

    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=409, detail="用户名已存在")

    allowed_pages = validate_allowed_pages(body.allowed_pages)
    user = User(
        username=username,
        hashed_password=hash_password("qwer1234"),
        role="user",
        allowed_pages_json=json.dumps(allowed_pages, ensure_ascii=False),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.put("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能修改管理员账号")

    if body.allowed_pages is not None:
        user.allowed_pages_json = json.dumps(
            validate_allowed_pages(body.allowed_pages),
            ensure_ascii=False,
        )

    if body.is_active is not None:
        if user_id == current_user.id:
            raise HTTPException(status_code=400, detail="不能停用当前登录用户")
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)
    return serialize_user(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账号")

    db.delete(user)
    db.commit()
    return {"id": user_id, "status": "deleted"}


@router.post("/{user_id}/reset-password")
def reset_password(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能重置管理员账号密码")

    user.hashed_password = hash_password("qwer1234")
    db.commit()
    return {"id": user_id, "status": "password_reset", "initial_password": "qwer1234"}
