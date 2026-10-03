from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseMixin


class PurchaseOrder(BaseMixin, Base):
    """采购单：ERP 采购模块主单据，串联供应商与收货入库。

    状态机（只在 service 层流转，禁止跳变）：
        draft（草稿，可编辑明细）→ submitted（已提交供应商，锁定明细）
        → receiving（收货中，部分收货）→ completed（全部收齐）
        cancelled 仅允许从 draft/submitted 撤销。

    total_amount 为明细下单快照（quantity × unit_price 之和），
    提交时计算固化，后续改价不影响历史单据。
    """

    __tablename__ = "purchase_orders"

    # 单号生成规则：PO + YYYYMMDD + 4 位序号（service 层保证唯一）
    po_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    total_amount: Mapped[float] = mapped_column(default=0.0)
    # 预计到货日期（ISO 字符串，演示级不做日期选择器强校验）
    expected_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 创建人（操作审计；Agent 生成的单据记系统用户 id）
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    # 明细：级联删除（删草稿单连带明细），分批收货更新 received_qty
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderItem.created_at",
    )


class PurchaseOrderItem(BaseMixin, Base):
    """采购单明细：按商品行下采购量，received_qty 支持分批收货。"""

    __tablename__ = "purchase_order_items"
    __table_args__ = (Index("ix_po_items_po", "purchase_order_id"),)

    purchase_order_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(default=0)
    unit_price: Mapped[float] = mapped_column(default=0.0)
    # 已收货数量：收货入库时累加，== quantity 视为该行收齐
    received_qty: Mapped[int] = mapped_column(default=0)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")

    @property
    def pending_qty(self) -> int:
        """剩余待收数量（不允许超收：service 层校验）。"""
        return max(0, self.quantity - self.received_qty)
