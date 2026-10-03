from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseMixin


class WarehouseLocation(BaseMixin, Base):
    """库位：单仓简版（仓库维度收敛为一个逻辑仓，不建 warehouses 表）。

    code 形如 A-01-02（区-巷道-层），供批次上架；无库位的批次
    （如系统初始化批次）location_id 为空。
    """

    __tablename__ = "warehouse_locations"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Batch(BaseMixin, Base):
    """库存批次：采购溯源 + 后续先进先出扣减的基础。

    两个来源：
    - 采购收货：po_item_id 非空，qty_initial = 本次收货量
    - 系统初始化：po_item_id 为空（存量商品的期初批次，一次性生成）

    qty_remaining：剩余可用量（盘点差异调整时同步修正）。
    演示级收敛：不含生产日期/有效期管理（P1 可扩展）。
    """

    __tablename__ = "batches"
    __table_args__ = (Index("ix_batches_product", "product_id"),)

    # 批次号规则：B + YYYYMMDD + 4 位序号（service 层保证唯一）
    batch_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    # 采购溯源：通过 po_item → purchase_order 可追溯到供应商
    po_item_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("purchase_order_items.id"), nullable=True
    )
    location_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("warehouse_locations.id"), nullable=True
    )
    qty_initial: Mapped[int] = mapped_column(default=0)
    qty_remaining: Mapped[int] = mapped_column(default=0)

    location: Mapped[Optional[WarehouseLocation]] = relationship()
