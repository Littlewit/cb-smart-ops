"""仓库路由：批次 / 库位 / 盘点（RBAC：查看 viewer，写操作 operator）。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.response import ok
from app.models import User
from app.services import warehouse_service

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])


class LocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: Optional[str] = Field(default=None, max_length=64)
    remark: Optional[str] = Field(default=None, max_length=255)


class CountedQtyUpdate(BaseModel):
    counted_qty: int = Field(ge=0)


@router.get("/batches")
async def list_batches(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    product_id: Optional[str] = Query(default=None),
):
    """批次列表（附商品 SKU 与库位编码）。"""
    return ok({"items": await warehouse_service.list_batches(db, product_id)})


@router.get("/locations")
async def list_locations(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """库位全量列表。"""
    items = await warehouse_service.list_locations(db)
    return ok(
        {
            "items": [
                {"id": l.id, "code": l.code, "name": l.name, "remark": l.remark}
                for l in items
            ],
            "total": len(items),
        }
    )


@router.post("/locations", status_code=201)
async def create_location(
    payload: LocationCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """新建库位（编码唯一）。"""
    loc = await warehouse_service.create_location(db, payload.code, payload.name, payload.remark)
    return ok({"id": loc.id, "code": loc.code})


@router.get("/stocktakings")
async def list_stocktakings(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """盘点单列表。"""
    return ok({"items": await warehouse_service.list_stocktakings(db)})


@router.post("/stocktakings", status_code=201)
async def create_stocktaking(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """创建盘点单（全量商品账面快照）。"""
    st = await warehouse_service.create_stocktaking(db, user.id)
    return ok({"id": st.id, "status": st.status, "item_count": len(st.items)})


@router.get("/stocktakings/{stocktaking_id}")
async def get_stocktaking(
    stocktaking_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """盘点单详情（明细附商品 SKU 与差异）。"""
    st = await warehouse_service.get_stocktaking_or_404(db, stocktaking_id)
    return ok(
        {
            "id": st.id,
            "status": st.status,
            "remark": st.remark,
            "created_at": st.created_at.isoformat(),
            "items": [
                {
                    "id": it.id,
                    "product_id": it.product_id,
                    "system_qty": it.system_qty,
                    "counted_qty": it.counted_qty,
                    "diff_qty": it.diff_qty,
                }
                for it in st.items
            ],
        }
    )


@router.put("/stocktakings/{stocktaking_id}/items/{item_id}")
async def update_counted_qty(
    stocktaking_id: str,
    item_id: str,
    payload: CountedQtyUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """录入实盘数（仅盘点中状态）。"""
    item = await warehouse_service.update_counted_qty(
        db, stocktaking_id, item_id, payload.counted_qty
    )
    return ok({"id": item.id, "counted_qty": item.counted_qty, "diff_qty": item.diff_qty})


@router.post("/stocktakings/{stocktaking_id}/complete")
async def complete_stocktaking(
    stocktaking_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """提交盘点：差异写 check 流水（账实分离）+ 修正批次剩余量。"""
    st = await warehouse_service.complete_stocktaking(db, stocktaking_id, user.id)
    return ok(
        {
            "id": st.id,
            "status": st.status,
            "adjusted_count": st.__dict__.get("adjusted_count", 0),
        }
    )
