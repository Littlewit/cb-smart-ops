"""库存路由：概览统计 / 流水查询 / 入库出库盘点。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.response import ok
from app.models import User
from app.schemas import InventoryLogOut, InventoryOpCreate
from app.services import inventory_service

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/summary")
async def inventory_summary(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """库存概览：商品总数/预警数/店铺数 + 预警商品列表（看板数据源）。"""
    return ok(await inventory_service.summary(db))


@router.get("/logs")
async def list_logs(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    product_id: Optional[str] = Query(default=None, description="按商品过滤"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """库存流水分页（按时间倒序），可按商品过滤。"""
    logs, total = await inventory_service.list_logs(db, product_id, page, page_size)
    return ok(
        {
            "items": [InventoryLogOut.model_validate(l).model_dump(mode="json") for l in logs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/logs", status_code=201)
async def create_log(
    payload: InventoryOpCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """入库/出库/盘点：余额与流水同事务更新，出库不足返回 400。"""
    log = await inventory_service.apply_inventory_op(db, payload, operator_id=user.id)
    return ok(InventoryLogOut.model_validate(log).model_dump(mode="json"))
