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
        email=payload.email,
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


async def reset_password(db: AsyncSession, username: str, email: str, new_password: str) -> None:
    """忘记密码：用户名 + 注册邮箱 匹配后重置密码。

    演示级方案：直接匹配后重置（无需登录）。
    安全说明：真实系统必须改为"邮箱验证码/时效重置链接"，
    否则存在邮箱枚举与越权重置风险——此处仅演示后端能力。
    """
    user = (
        await db.execute(
            select(User).where(User.username == username, User.email == email)
        )
    ).scalar_one_or_none()
    # 统一文案不区分"用户不存在/邮箱不匹配"，防信息枚举
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "用户名或邮箱不匹配")
    user.password_hash = security.hash_password(new_password)
    await db.flush()


async def change_password(
    db: AsyncSession, user: User, old_password: str, new_password: str
) -> None:
    """已登录用户修改密码：需验证旧密码（防止会话被劫持后直接改密）。"""
    if not security.verify_password(old_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "旧密码错误")
    user.password_hash = security.hash_password(new_password)
    await db.flush()


def update_email(user: User, email: str) -> None:
    """更新邮箱（同步函数：纯属性赋值；忘记密码的匹配依据随之更新）。

    注意：改邮箱后，旧"用户名+旧邮箱"组合将无法再重置密码——
    属预期行为（邮箱是身份凭证的一部分，变更即生效）。
    """
    user.email = email
