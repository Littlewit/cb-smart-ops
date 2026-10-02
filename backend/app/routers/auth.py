"""认证路由：注册 / 登录（图形验证码）/ 忘记密码重置（公开）+ 修改密码（需登录）。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import captcha
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models import User
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    UserCreate,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/captcha")
async def get_captcha():
    """获取图形验证码：返回 captcha_id 与 base64 PNG 图片。

    登录时必须回传 captcha_id + 用户输入（一次性校验，防暴力破解）。
    """
    captcha_id, _, image_b64 = captcha.issue()
    return ok({"captcha_id": captcha_id, "image": f"data:image/png;base64,{image_b64}"})


@router.post("/register", status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """注册用户：用户名唯一，密码仅接收明文并立即哈希。"""
    user = await auth_service.register(db, payload)
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录：先校验图形验证码（一次性），再验证账密返回 JWT。

    验证码失败统一 400 且不透漏具体原因细节（过期/错误对用户展示同一文案）。
    """
    if not captcha.verify(payload.captcha_id, payload.captcha_code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "验证码错误或已过期")
    token = await auth_service.login(db, payload)
    return ok({"access_token": token, "token_type": "bearer"})


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """忘记密码：用户名 + 注册邮箱 匹配后直接设置新密码（无需登录）。

    演示级方案；生产必须改为邮箱验证码/时效链接（见 schema 注释）。
    """
    await auth_service.reset_password(db, payload.username, payload.email, payload.new_password)
    return ok(message="密码已重置，请使用新密码登录")


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改密码（需登录）：验证旧密码后设置新密码。"""
    await auth_service.change_password(db, user, payload.old_password, payload.new_password)
    return ok(message="密码修改成功")
