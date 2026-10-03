from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class OrderItem(BaseMixin, Base):
    """订单明细：拉单时从平台订单项快照落库（拆单/发货/对账的依据）。

    platform_sku 保留平台侧原始 SKU（对账可对回平台）；
    product_id 关联本地商品（拉单时按 shop + sku 匹配，匹配不到的项丢弃）。
    """

    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_order", "order_id"),)

    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    platform_sku: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int] = mapped_column(default=0)
    price: Mapped[float] = mapped_column(default=0.0)
