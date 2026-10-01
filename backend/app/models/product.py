from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class Product(BaseMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("shop_id", "sku", name="uq_products_shop_sku"),
        Index("ix_products_alert_status", "alert_status"),
    )

    shop_id: Mapped[str] = mapped_column(String(36), ForeignKey("shops.id"))
    sku: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    cost_price: Mapped[float] = mapped_column(default=0.0)
    sale_price: Mapped[float] = mapped_column(default=0.0)
    stock: Mapped[int] = mapped_column(default=0)
    safety_stock: Mapped[int] = mapped_column(default=10)
    alert_status: Mapped[bool] = mapped_column(default=False)


class ProductSkuMapping(BaseMixin, Base):
    """多平台 SKU 映射：一个内部商品关联多个平台店铺的外部 SKU。"""

    __tablename__ = "product_sku_mappings"
    __table_args__ = (
        UniqueConstraint("platform", "external_sku", name="uq_sku_mappings_platform_external"),
    )

    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"))
    platform: Mapped[str] = mapped_column(String(20))
    external_sku: Mapped[str] = mapped_column(String(64))
