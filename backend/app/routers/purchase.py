"""采购路由：供应商 / 采购单状态机 / 收货入库。

RBAC：查看 viewer；供应商与采购单写操作 operator；收货入库 operator
（收货改变库存与批次，属运营操作）。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.response import ok
from app.models import User
from app.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    ReceiveRequest,
    SupplierCreate,
    SupplierUpdate,
)
from app.services import purchase_service

router = APIRouter(prefix="/api", tags=["procurement"])


# ---------- 供应商 ----------


@router.get("/suppliers")
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """供应商全量列表（主数据量小不分页）。"""
    items = await purchase_service.list_suppliers(db)
    return ok({"items": items, "total": len(items)})


@router.post("/suppliers", status_code=201)
async def create_supplier(
    payload: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """新建供应商（名称唯一）。"""
    sup = await purchase_service.create_supplier(db, payload)
    return ok({"id": sup.id, "name": sup.name})


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """更新供应商（部分更新；停用后不可下新单）。"""
    sup = await purchase_service.update_supplier(db, supplier_id, payload)
    return ok({"id": sup.id, "name": sup.name, "status": sup.status})


# ---------- 采购单 ----------


@router.get("/purchase-orders")
async def list_purchase_orders(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    status: Optional[str] = Query(default=None, description="draft/submitted/receiving/completed/cancelled"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """采购单分页列表（可按状态过滤）。"""
    items, total = await purchase_service.list_pos(db, status, page, page_size)
    return ok(
        {
            "items": [
                {
                    "id": p.id,
                    "po_no": p.po_no,
                    "supplier_id": p.supplier_id,
                    "status": p.status,
                    "total_amount": p.total_amount,
                    "expected_date": p.expected_date,
                    "remark": p.remark,
                    "created_at": p.created_at.isoformat(),
                }
                for p in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/purchase-orders/{po_id}")
async def get_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """采购单详情（主单 + 明细）。"""
    return ok(await purchase_service.get_po_detail(db, po_id))


@router.post("/purchase-orders", status_code=201)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """新建草稿采购单（固化金额快照；Agent 生成亦走此服务层）。"""
    po = await purchase_service.create_po(db, payload, user.id)
    return ok({"id": po.id, "po_no": po.po_no, "status": po.status})


@router.put("/purchase-orders/{po_id}")
async def update_purchase_order(
    po_id: str,
    payload: PurchaseOrderUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """编辑采购单（仅草稿；明细全量替换）。"""
    po = await purchase_service.update_po(db, po_id, payload)
    return ok({"id": po.id, "po_no": po.po_no, "status": po.status})


@router.post("/purchase-orders/{po_id}/submit")
async def submit_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """提交采购单（draft → submitted，明细锁定）。"""
    po = await purchase_service.submit_po(db, po_id)
    return ok({"id": po.id, "status": po.status})


@router.post("/purchase-orders/{po_id}/cancel")
async def cancel_purchase_order(
    po_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """撤销采购单（仅 draft/submitted）。"""
    po = await purchase_service.cancel_po(db, po_id)
    return ok({"id": po.id, "status": po.status})


@router.post("/purchase-orders/{po_id}/receive")
async def receive_purchase_order(
    po_id: str,
    payload: ReceiveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """收货入库：生成批次 + 账实分离写流水（单事务，任一行非法整体回滚）。"""
    po = await purchase_service.receive_po(db, po_id, payload, user.id)
    return ok({"id": po.id, "po_no": po.po_no, "status": po.status})
