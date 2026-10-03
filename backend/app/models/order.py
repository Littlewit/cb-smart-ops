from typing import Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class Order(BaseMixin, Base):
    """平台订单：由 Mock 平台拉取（幂等：shop_id + platform_order_no 唯一）。

    状态机（ERP 扩展后）：
        legacy  — 迁移前存量的演示数据（seed 脚本生成，订单页不展示）
        pending — 已拉取待拆单
        partial — 已拆单但仍有商品项因库存不足未发货
        shipped — 全部发货单已发货
    老代码写死的 pending/shipped/done 值保留兼容，订单页过滤 legacy。
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("shop_id", "platform_order_no", name="uq_orders_shop_no"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_status", "status"),
    )

    shop_id: Mapped[str] = mapped_column(String(36), ForeignKey("shops.id"))
    platform_order_no: Mapped[str] = mapped_column(String(64))
    # legacy / pending / partial / shipped（兼容历史 pending/shipped/done）
    # 索引在 __table_args__ 显式定义（index=True 会生成同名隐式索引导致 create_all 冲突）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    amount: Mapped[float] = mapped_column(default=0.0)
    # 来源平台标识（mock / shein / shopify，拉单时从 shop.platform 快照）
    platform: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # 收货人信息（拆单/发货面单用；从平台订单源快照）
    receiver_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    receiver_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    receiver_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # 全部发货完成时间（报表"发货时效"计算依据）
    shipped_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
