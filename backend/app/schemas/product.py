"""商品与多平台 SKU 映射相关 Schema。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    shop_id: str = Field(description="所属店铺 ID")
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    cost_price: float = Field(default=0.0, ge=0, description="成本价")
    sale_price: float = Field(default=0.0, ge=0, description="售价")
    stock: int = Field(default=0, ge=0, description="当前库存")
    safety_stock: int = Field(default=10, ge=0, description="安全库存阈值")


class ProductUpdate(BaseModel):
    """部分更新：仅非 None 字段生效；库存字段更新后自动刷新预警状态。"""

    name: Optional[str] = Field(default=None, max_length=255)
    cost_price: Optional[float] = Field(default=None, ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0)
    safety_stock: Optional[int] = Field(default=None, ge=0)


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    shop_id: str
    sku: str
    name: str
    cost_price: float
    sale_price: float
    stock: int
    safety_stock: int
    alert_status: bool


class SkuMappingCreate(BaseModel):
    platform: Literal["shein", "shopify", "mock"]
    external_sku: str = Field(min_length=1, max_length=64, description="平台侧 SKU 编号")


class SkuMappingOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    product_id: str
    platform: str
    external_sku: str
