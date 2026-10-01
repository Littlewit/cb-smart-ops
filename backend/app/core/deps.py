"""FastAPI 公共依赖：JWT 认证 + RBAC 角色校验。

角色采用硬编码 3 级（admin > operator > viewer），require_role 校验"最低等级"，
不做权限点配置化（演示项目收敛范围，见需求文档 §2）。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

import jwt as pyjwt

from app.core import security
from app.core.database import get_db
from app.models import User

# Bearer Token 提取器；auto_error=False 以便自行返回统一的 401 响应
bearer_scheme = HTTPBearer(auto_error=False)

# 角色权限等级：数值越大权限越高
ROLE_LEVELS = {"viewer": 0, "operator": 1, "admin": 2}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """解析 JWT 并加载当前用户；任何一步失败统一返回 401。"""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未提供认证信息")
    try:
        payload = security.decode_access_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token 无效或已过期")
    # sub 存的是用户 ID（字符串形式）
    user = await db.get(User, payload.get("sub", ""))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return user


def require_role(minimum_role: str):
    """角色依赖工厂：要求当前用户角色等级 >= minimum_role。

    用法（router 内声明式挂载）：
        user: User = Depends(require_role("operator"))
    viewer(0) < operator(1) < admin(2)，高级别角色可通过低级别接口。
    """

    async def checker(user: User = Depends(get_current_user)) -> User:
        if ROLE_LEVELS.get(user.role, -1) < ROLE_LEVELS[minimum_role]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"需要 {minimum_role} 及以上权限"
            )
        return user

    return checker
