from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseMixin


class Shipment(BaseMixin, Base):
    """发货单：订单拆单的结果单元。

    拆单规则（演示级收敛）：按订单分组内各商品项的库存充足性二分——
    库存充足的项合入一个发货单（waiting），不足的项留在订单 pending
    状态并触发预警；发货时填写物流单号并扣减库存（账实分离）。
    """

    __tablename__ = "shipments"
    __table_args__ = (Index("ix_shipments_order", "order_id"),)

    # 引用 orders 表的行（一行 = 一条平台订单）
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    # waiting（待发货）/ shipped（已发货）
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    tracking_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shipped_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    items: Mapped[list["ShipmentItem"]] = relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="ShipmentItem.created_at",
    )


class ShipmentItem(BaseMixin, Base):
    """发货单明细：拆单后归属到本发货单的商品行。"""

    __tablename__ = "shipment_items"
    __table_args__ = (Index("ix_shipment_items_shipment", "shipment_id"),)

    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(default=0)

    shipment: Mapped[Shipment] = relationship(back_populates="items")
