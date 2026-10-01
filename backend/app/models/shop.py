from typing import Optional

from sqlalchemy import LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class Shop(BaseMixin, Base):
    __tablename__ = "shops"
    __table_args__ = (UniqueConstraint("platform", "name", name="uq_shops_platform_name"),)

    # shein / shopify / mock
    platform: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(128))
    # AES-256-GCM 密文，接口永不回显明文
    credentials_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    # active / disconnected
    status: Mapped[str] = mapped_column(String(20), default="active")
