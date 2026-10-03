from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseMixin


class Stocktaking(BaseMixin, Base):
    """盘点单：全仓维度盘点（演示级收敛，不做局部盘点）。

    状态机：processing（盘点中，可录入实盘数）→ completed（已提交，
    差异按 check 流水写入账实分离体系并同步批次剩余量）。
    """

    __tablename__ = "stocktakings"

    status: Mapped[str] = mapped_column(String(20), default="processing")
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 盘点发起人
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    items: Mapped[list["StocktakingItem"]] = relationship(
        back_populates="stocktaking",
        cascade="all, delete-orphan",
        order_by="StocktakingItem.created_at",
    )


class StocktakingItem(BaseMixin, Base):
    """盘点明细：system_qty 为发起时的账面库存快照，counted_qty 为实盘数。"""

    __tablename__ = "stocktaking_items"
    __table_args__ = (Index("ix_stocktaking_items_stocktaking", "stocktaking_id"),)

    stocktaking_id: Mapped[str] = mapped_column(ForeignKey("stocktakings.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    system_qty: Mapped[int] = mapped_column(default=0)
    # 实盘数量：录入后与 system_qty 的差异即为盘盈/盘亏
    counted_qty: Mapped[int | None] = mapped_column(nullable=True)

    stocktaking: Mapped[Stocktaking] = relationship(back_populates="items")

    @property
    def diff_qty(self) -> Optional[int]:
        """差异 = 实盘 − 账面（正=盘盈，负=盘亏，None=未录入）。"""
        if self.counted_qty is None:
            return None
        return self.counted_qty - self.system_qty
