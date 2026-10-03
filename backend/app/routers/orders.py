"""订单路由：拉单 / 拆单 / 发货流转（RBAC：查看 viewer，操作 operator）。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import User
from app.schemas.order import FetchOrdersRequest, ShipRequest, SplitOrdersRequest
from app.services import order_service

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders")
async def list_orders(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    status: Optional[str] = Query(default=None, description="pending/partial/shipped/legacy"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """订单分页列表（默认排除 legacy 历史数据，附明细）。"""
    items, total = await order_service.list_orders(db, status, page, page_size)
    return ok(
        {
            "items": [
                {
                    "id": o.id,
                    "platform_order_no": o.platform_order_no,
                    "platform": o.platform,
                    "status": o.status,
                    "amount": o.amount,
                    "receiver_name": o.receiver_name,
                    "receiver_phone": o.receiver_phone,
                    "receiver_address": o.receiver_address,
                    "shipped_at": o.shipped_at,
                    "created_at": o.created_at.isoformat(),
                    "items": [
                        {
                            "id": it.id,
                            "product_id": it.product_id,
                            "platform_sku": it.platform_sku,
                            "quantity": it.quantity,
                            "price": it.price,
                        }
                        for it in o.items
                    ],
                }
                for o in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/orders/fetch")
async def fetch_orders(
    payload: FetchOrdersRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """按店铺拉取平台订单（幂等：重复拉取自动跳过已入库订单）。"""
    result = await order_service.fetch_orders(db, payload.shop_id, payload.limit, user.id)
    return ok(result)


@router.post("/orders/split")
async def split_orders(
    payload: SplitOrdersRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """一键拆单：pending 订单按库存充足性生成发货单（不足项保持 pending）。"""
    return ok(await order_service.split_orders(db, payload.order_id, user.id))


@router.get("/shipments")
async def list_shipments(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    status: Optional[str] = Query(default=None, description="waiting/shipped"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """发货单分页列表（附平台单号与明细）。"""
    rows, total = await order_service.list_shipments(db, status, page, page_size)
    return ok(
        {
            "items": [
                {
                    "id": sh.id,
                    "order_id": sh.order_id,
                    "platform_order_no": order_no,
                    "status": sh.status,
                    "tracking_no": sh.tracking_no,
                    "carrier": sh.carrier,
                    "shipped_at": sh.shipped_at,
                    "created_at": sh.created_at.isoformat(),
                    "items": [
                        {
                            "id": it.id,
                            "product_id": it.product_id,
                            "quantity": it.quantity,
                        }
                        for it in sh.items
                    ],
                }
                for sh, order_no in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/shipments/{shipment_id}/ship")
async def ship_shipment(
    shipment_id: str,
    payload: ShipRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """发货：扣减库存（账实分离）+ 状态流转；订单全部发完自动完成。"""
    sh = await order_service.ship_shipment(
        db, shipment_id, payload.tracking_no, payload.carrier, user.id
    )
    return ok({"id": sh.id, "status": sh.status, "tracking_no": sh.tracking_no})
