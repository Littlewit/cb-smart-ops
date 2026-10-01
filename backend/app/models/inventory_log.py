from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class InventoryLog(BaseMixin, Base):
    """库存流水：入库/出库/盘点，与 products.stock 同事务更新（账实分离）。"""

    __tablename__ = "inventory_logs"
    __table_args__ = (Index("ix_inventory_logs_product_created", "product_id", "created_at"),)

    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"))
    # in / out / check
    type: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(default=0)
    stock_before: Mapped[int] = mapped_column(default=0)
    stock_after: Mapped[int] = mapped_column(default=0)
    reason: Mapped[str] = mapped_column(String(255), default="")
    operator_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
