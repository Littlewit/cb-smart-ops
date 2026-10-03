"""采购模块 Schema：供应商 / 采购单 / 收货请求。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------- 供应商 ----------
class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    contact: Optional[str] = Field(default=None, max_length=64)
    phone: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=120)


class SupplierUpdate(BaseModel):
    """供应商更新：全可选，只更新传入字段。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    contact: Optional[str] = Field(default=None, max_length=64)
    phone: Optional[str] = Field(default=None, max_length=32)
    email: Optional[str] = Field(default=None, max_length=120)
    status: Optional[Literal["active", "disabled"]] = None


class SupplierOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    contact: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    status: str


# ---------- 采购单 ----------
class PurchaseOrderItemIn(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, description="采购数量 > 0")
    unit_price: float = Field(ge=0, description="采购单价 >= 0")


class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    expected_date: Optional[str] = Field(default=None, max_length=20)
    remark: Optional[str] = Field(default=None, max_length=255)
    items: list[PurchaseOrderItemIn] = Field(min_length=1)


class PurchaseOrderItemUpdate(BaseModel):
    """草稿编辑：明细全量替换语义。"""

    product_id: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class PurchaseOrderUpdate(BaseModel):
    """仅草稿可编辑：换供应商/备注/整批替换明细。"""

    supplier_id: Optional[str] = None
    expected_date: Optional[str] = Field(default=None, max_length=20)
    remark: Optional[str] = Field(default=None, max_length=255)
    items: Optional[list[PurchaseOrderItemUpdate]] = None


class PurchaseOrderItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    product_id: str
    quantity: int
    unit_price: float
    received_qty: int


class PurchaseOrderOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    po_no: str
    supplier_id: str
    status: str
    total_amount: float
    expected_date: Optional[str]
    remark: Optional[str]
    created_by: Optional[str]


class PurchaseOrderDetailOut(PurchaseOrderOut):
    """详情：附明细列表（前端抽屉渲染）。"""

    items: list[PurchaseOrderItemOut]


# ---------- 收货 ----------
class ReceiveItemIn(BaseModel):
    """一次收货行：明细 ID + 本次实收数量 + 上架库位（可空）。"""

    item_id: str
    quantity: int = Field(gt=0)
    location_id: Optional[str] = None


class ReceiveRequest(BaseModel):
    items: list[ReceiveItemIn] = Field(min_length=1)
