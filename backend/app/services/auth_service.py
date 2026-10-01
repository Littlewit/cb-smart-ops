"""认证业务：注册 / 登录。

密码只存 bcrypt 哈希；登录成功签发 JWT（payload 含角色快照）。
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import User
from app.schemas import LoginRequest, UserCreate


async def register(db: AsyncSession, payload: UserCreate) -> User:
    """注册新用户；用户名唯一冲突返回 409。"""
    exists = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")

    user = User(
        username=payload.username,
        password_hash=security.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    # flush 使主键与默认值生效，但不提交（由 get_db 统一提交）
    await db.flush()
    await db.refresh(user)
    return user


async def login(db: AsyncSession, payload: LoginRequest) -> str:
    """校验用户名密码，成功返回 JWT；失败统一返回 401（不区分用户不存在/密码错误）。"""
    user = (
        await db.execute(select(User).where(User.username == payload.username))
    ).scalar_one_or_none()
    if user is None or not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    return security.create_access_token(user.id, user.role)
