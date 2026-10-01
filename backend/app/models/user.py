from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class User(BaseMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # admin / operator / viewer（RBAC 硬编码 3 角色，无权限表）
    role: Mapped[str] = mapped_column(String(20), default="operator")
