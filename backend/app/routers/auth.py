"""认证路由：注册 / 登录（公开接口，无需 Token）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ok
from app.schemas import LoginRequest, UserCreate, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """注册用户：用户名唯一，密码仅接收明文并立即哈希。"""
    user = await auth_service.register(db, payload)
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录：成功返回 JWT（前端存 Pinia + localStorage，请求头携带）。"""
    token = await auth_service.login(db, payload)
    return ok({"access_token": token, "token_type": "bearer"})
