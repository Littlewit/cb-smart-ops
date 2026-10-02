from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class User(BaseMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # 邮箱：注册必填；忘记密码时用于"用户名+邮箱"匹配重置（演示级方案，
    # 生产应改为邮箱验证码/链接，见 auth_service.reset_password 注释）
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # admin / operator / viewer（RBAC 硬编码 3 角色，无权限表）
    role: Mapped[str] = mapped_column(String(20), default="operator")
