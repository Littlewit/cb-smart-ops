from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class Order(BaseMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("shop_id", "platform_order_no", name="uq_orders_shop_no"),
        Index("ix_orders_created_at", "created_at"),
    )

    shop_id: Mapped[str] = mapped_column(String(36), ForeignKey("shops.id"))
    platform_order_no: Mapped[str] = mapped_column(String(64))
    # pending / shipped / done
    status: Mapped[str] = mapped_column(String(20), default="pending")
    amount: Mapped[float] = mapped_column(default=0.0)
