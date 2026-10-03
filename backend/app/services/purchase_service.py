"""采购业务：供应商 / 采购单状态机 / 收货入库（生成批次 + 账实分离流水）。

状态机：draft → submitted → receiving → completed；draft/submitted 可 cancelled。
单号规则：PO/B + YYYYMMDD + 4 位当日序号（查当日最大序号后自增，单进程内安全）。
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Batch,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)
from app.schemas.inventory import InventoryOpCreate
from app.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderItemOut,
    PurchaseOrderUpdate,
    ReceiveRequest,
    SupplierCreate,
    SupplierUpdate,
)
from app.services.inventory_service import apply_inventory_op

# 合法状态流转表：from -> 允许的 to 集合
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"receiving", "cancelled"},
    "receiving": {"completed"},
    "completed": set(),
    "cancelled": set(),
}

# ---------- 单号 ----------


async def _next_seq(db: AsyncSession, model, column, prefix: str) -> int:
    """取当日已有单号的最大序号 + 1（同前缀 LIKE 匹配）。"""
    like = f"{prefix}%"
    rows = (await db.execute(select(column).where(column.like(like)))).scalars().all()
    seq = 0
    for no in rows:
        try:
            seq = max(seq, int(str(no).removeprefix(prefix)))
        except ValueError:
            continue
    return seq + 1


async def gen_po_no(db: AsyncSession) -> str:
    """采购单号：PO + YYYYMMDD + 4 位序号，如 PO-20261003-0001。"""
    prefix = f"PO-{datetime.now():%Y%m%d}-"
    seq = await _next_seq(db, PurchaseOrder, PurchaseOrder.po_no, prefix)
    return f"{prefix}{seq:04d}"


async def gen_batch_no(db: AsyncSession) -> str:
    """批次号：B + YYYYMMDD + 4 位序号，如 B-20261003-0001。"""
    prefix = f"B-{datetime.now():%Y%m%d}-"
    seq = await _next_seq(db, Batch, Batch.batch_no, prefix)
    return f"{prefix}{seq:04d}"


# ---------- 供应商 ----------


async def create_supplier(db: AsyncSession, payload: SupplierCreate) -> Supplier:
    """新建供应商：名称唯一冲突返回 409。"""
    exists = (
        await db.execute(select(Supplier).where(Supplier.name == payload.name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "供应商名称已存在")
    sup = Supplier(**payload.model_dump())
    db.add(sup)
    await db.flush()
    await db.refresh(sup)
    return sup


async def update_supplier(
    db: AsyncSession, supplier_id: str, payload: SupplierUpdate
) -> Supplier:
    """更新供应商（部分更新）；停用不影响历史采购单。"""
    sup = await db.get(Supplier, supplier_id)
    if sup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "供应商不存在")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] != sup.name:
        dup = (
            await db.execute(select(Supplier).where(Supplier.name == data["name"]))
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "供应商名称已存在")
    for k, v in data.items():
        setattr(sup, k, v)
    await db.flush()
    await db.refresh(sup)
    return sup


async def list_suppliers(db: AsyncSession) -> list[Supplier]:
    """供应商全量列表（主数据量小，不分页）。"""
    return list((await db.execute(select(Supplier).order_by(Supplier.created_at))).scalars())


# ---------- 采购单 ----------


async def get_po_or_404(db: AsyncSession, po_id: str) -> PurchaseOrder:
    """取采购单（预加载 items：async session 下 lazy 关系同步访问会 MissingGreenlet）。"""
    po = (
        await db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(selectinload(PurchaseOrder.items))
        )
    ).scalar_one_or_none()
    if po is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "采购单不存在")
    return po


async def _calc_total(db: AsyncSession, items: list) -> float:
    """按明细快照计算总金额（quantity × unit_price 之和）。"""
    total = 0.0
    for it in items:
        total += it.quantity * it.unit_price
    return round(total, 2)


async def _validate_supplier(db: AsyncSession, supplier_id: str) -> None:
    """供应商必须存在且启用（停用供应商不可下新单）。"""
    sup = await db.get(Supplier, supplier_id)
    if sup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "供应商不存在")
    if sup.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "供应商已停用，不可下采购单")


async def create_po(
    db: AsyncSession, payload: PurchaseOrderCreate, user_id: Optional[str]
) -> PurchaseOrder:
    """新建草稿采购单：校验供应商/商品存在，固化金额快照。"""
    await _validate_supplier(db, payload.supplier_id)
    product_ids = [it.product_id for it in payload.items]
    found = set(
        (await db.execute(select(Product.id).where(Product.id.in_(product_ids)))).scalars()
    )
    missing = set(product_ids) - found
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"商品不存在: {sorted(missing)}")

    po = PurchaseOrder(
        po_no=await gen_po_no(db),
        supplier_id=payload.supplier_id,
        status="draft",
        total_amount=await _calc_total(db, payload.items),
        expected_date=payload.expected_date,
        remark=payload.remark,
        created_by=user_id,
    )
    db.add(po)
    await db.flush()
    for it in payload.items:
        db.add(
            PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=it.product_id,
                quantity=it.quantity,
                unit_price=it.unit_price,
            )
        )
    await db.flush()
    return po


async def update_po(
    db: AsyncSession, po_id: str, payload: PurchaseOrderUpdate
) -> PurchaseOrder:
    """编辑采购单：仅 draft 状态可改；明细全量替换并重算金额。"""
    po = await get_po_or_404(db, po_id)
    if po.status != "draft":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"仅草稿状态可编辑（当前 {po.status}）")

    data = payload.model_dump(exclude_unset=True)
    if "supplier_id" in data and data["supplier_id"]:
        await _validate_supplier(db, data["supplier_id"])
        po.supplier_id = data["supplier_id"]
    for k in ("expected_date", "remark"):
        if k in data:
            setattr(po, k, data[k])
    if payload.items is not None:
        # 全量替换明细（ORM 级联删除旧明细 + 新增）
        po.items = [
            PurchaseOrderItem(product_id=it.product_id, quantity=it.quantity, unit_price=it.unit_price)
            for it in payload.items
        ]
        po.total_amount = await _calc_total(db, po.items)
    await db.flush()
    await db.refresh(po)
    return po


async def _transition(db: AsyncSession, po: PurchaseOrder, to: str) -> None:
    """状态流转：非法流转一律 400（状态机收敛在 service 层）。"""
    if to not in _TRANSITIONS.get(po.status, set()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"非法状态流转：{po.status} → {to}",
        )
    po.status = to


async def submit_po(db: AsyncSession, po_id: str) -> PurchaseOrder:
    """提交采购单：draft → submitted，明细锁定。"""
    po = await get_po_or_404(db, po_id)
    await _transition(db, po, "submitted")
    await db.flush()
    return po


async def cancel_po(db: AsyncSession, po_id: str) -> PurchaseOrder:
    """撤销采购单：仅 draft/submitted 可撤销（已收货不可撤销，走退货流程——P1）。"""
    po = await get_po_or_404(db, po_id)
    await _transition(db, po, "cancelled")
    await db.flush()
    return po


async def list_pos(
    db: AsyncSession, status_filter: Optional[str], page: int, page_size: int
) -> tuple[list[PurchaseOrder], int]:
    """采购单分页列表（可按状态过滤）。"""
    query = select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    count_query = select(func.count(PurchaseOrder.id))
    if status_filter:
        query, count_query = query.where(PurchaseOrder.status == status_filter), (
            count_query.where(PurchaseOrder.status == status_filter)
        )
    total = (await db.execute(count_query)).scalar_one()
    items = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
    )
    return items, total


async def get_po_detail(db: AsyncSession, po_id: str) -> dict:
    """采购单详情：主单 + 明细（前端抽屉渲染）。"""
    po = await get_po_or_404(db, po_id)
    return {
        "id": po.id,
        "po_no": po.po_no,
        "supplier_id": po.supplier_id,
        "status": po.status,
        "total_amount": po.total_amount,
        "expected_date": po.expected_date,
        "remark": po.remark,
        "created_by": po.created_by,
        "items": [
            PurchaseOrderItemOut.model_validate(it).model_dump(mode="json")
            for it in po.items
        ],
    }


# ---------- 收货入库 ----------


async def receive_po(
    db: AsyncSession, po_id: str, payload: ReceiveRequest, user_id: Optional[str]
) -> PurchaseOrder:
    """收货入库：分批收货的核心事务。

    对每个收货行：
    1. 校验明细归属与超收（received + qty <= order qty）
    2. 生成批次（qty_initial = qty_remaining = 实收量，关联 po_item 溯源）
    3. 复用 apply_inventory_op 写 in 流水 + 更新余额（账实分离同事务）
    全部明细收齐 → completed；否则 → receiving。
    """
    po = await get_po_or_404(db, po_id)
    if po.status not in ("submitted", "receiving"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"当前状态 {po.status} 不可收货（仅 submitted/receiving）",
        )

    items_map = {it.id: it for it in po.items}
    for line in payload.items:
        item = items_map.get(line.item_id)
        if item is None or item.purchase_order_id != po.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"明细不存在: {line.item_id}")
        if line.quantity > item.pending_qty:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"超收：明细 {item.id[:8]} 待收 {item.pending_qty}，本次 {line.quantity}",
            )

    # 先全部校验再执行（任一行非法则整个收货事务回滚，不留半收状态）
    for line in payload.items:
        item = items_map[line.item_id]
        # 1) 生成批次（采购溯源）
        batch = Batch(
            batch_no=await gen_batch_no(db),
            product_id=item.product_id,
            po_item_id=item.id,
            location_id=line.location_id,
            qty_initial=line.quantity,
            qty_remaining=line.quantity,
        )
        db.add(batch)
        # 2) 账实分离：in 流水 + 余额更新（apply_inventory_op 只 flush，同事务）
        await apply_inventory_op(
            db,
            InventoryOpCreate(
                product_id=item.product_id,
                type="in",
                quantity=line.quantity,
                reason=f"采购收货 {po.po_no}",
            ),
            user_id,
        )
        # 3) 累加已收数量
        item.received_qty += line.quantity

    all_done = all(it.received_qty >= it.quantity for it in po.items)
    po.status = "completed" if all_done else "receiving"
    await db.flush()
    return po
