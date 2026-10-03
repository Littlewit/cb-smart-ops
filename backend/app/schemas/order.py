"""订单模块 Schema：拉单请求 / 拆单请求 / 发货请求。"""

from typing import Optional

from pydantic import BaseModel, Field


class FetchOrdersRequest(BaseModel):
    """按店铺拉取平台订单（幂等：重复拉取已入库订单自动跳过）。"""

    shop_id: str
    limit: int = Field(default=5, ge=1, le=20, description="本次最多拉取条数")


class SplitOrdersRequest(BaseModel):
    """一键拆单：不传 order_id 则拆所有 pending 订单。"""

    order_id: Optional[str] = None


class ShipRequest(BaseModel):
    """发货：填写物流信息并扣减库存（账实分离）。"""

    tracking_no: str = Field(min_length=1, max_length=64)
    carrier: Optional[str] = Field(default=None, max_length=32)
