"""库存操作与流水相关 Schema。"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class InventoryOpCreate(BaseModel):
    """入库 / 出库 / 盘点 操作请求。

    - in   ：入库，quantity 为增加数量，after = before + quantity
    - out   ：出库，quantity 为减少数量，after = before - quantity（库存不足报 400）
    - check ：盘点，quantity 为实盘数量，after = quantity
    """

    product_id: str
    type: Literal["in", "out", "check"]
    quantity: int = Field(ge=0)
    reason: str = Field(default="", max_length=255, description="操作原因，空则自动生成")


class InventoryLogOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    product_id: str
    type: str
    quantity: int
    stock_before: int
    stock_after: int
    reason: str
    created_at: datetime


class InventorySummary(BaseModel):
    """库存概览（看板顶部卡片 + 预警列表的数据来源）。"""

    total_products: int
    alert_count: int
    total_shops: int
    alert_products: list  # ProductOut 列表，由路由层组装
