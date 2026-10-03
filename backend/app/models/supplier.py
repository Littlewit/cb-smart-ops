from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class Supplier(BaseMixin, Base):
    """供应商：采购主数据（ERP 采购模块的起点）。

    status: active（可下单）/ disabled（停用，停用后不可新建采购单，
    历史采购单不受影响——保留追溯能力）。
    """

    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
