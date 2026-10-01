"""店铺相关 Schema：创建 / 更新 / 输出。

凭证（credentials）仅在创建/更新时以明文传入，落库前 AES 加密，
任何输出 Schema 都不包含凭证字段（接口永不回显）。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ShopCreate(BaseModel):
    platform: Literal["shein", "shopify", "mock"] = Field(description="平台类型")
    name: str = Field(min_length=1, max_length=128, description="店铺名，同平台内唯一")
    credentials: str = Field(default="", description="平台 API 凭证（明文，仅此一次传入）")


class ShopUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    credentials: Optional[str] = Field(default=None, description="传入则重新加密")
    status: Optional[Literal["active", "disconnected"]] = None


class ShopOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    platform: str
    name: str
    status: str
