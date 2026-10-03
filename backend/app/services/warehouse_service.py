"""仓库业务：批次查询 / 库位管理 / 盘点（差异写账实分离流水）。

盘点闭环（演示级收敛）：
    创建盘点单（全量商品账面快照）→ 录入实盘数 → 提交：
    差异 ≠ 0 的项按 check 流水调整余额（复用 apply_inventory_op），
    并同步修正该商品最新批次的 qty_remaining（无批次商品仅调余额）。
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Batch,
    InventoryLog,
    Product,
    Stocktaking,
    StocktakingItem,
    WarehouseLocation,
)
from app.schemas.inventory import InventoryOpCreate
from app.services.inventory_service import apply_inventory_op


# ---------- 批次 ----------


async def list_batches(db: AsyncSession, product_id: Optional[str] = None) -> list[dict]:
    """批次列表（附商品 SKU 与库位编码，按创建倒序，上限 200 行）。"""
    query = (
        select(Batch, Product.sku, WarehouseLocation.code)
        .join(Product, Batch.product_id == Product.id)
        .outerjoin(WarehouseLocation, Batch.location_id == WarehouseLocation.id)
        .order_by(Batch.created_at.desc())
        .limit(200)
    )
    if product_id:
        query = query.where(Batch.product_id == product_id)
    rows = (await db.execute(query)).all()
    return [
        {
            "id": b.id,
            "batch_no": b.batch_no,
            "product_id": b.product_id,
            "product_sku": sku,
            "po_item_id": b.po_item_id,
            "location_code": code,
            "qty_initial": b.qty_initial,
            "qty_remaining": b.qty_remaining,
            "created_at": b.created_at.isoformat(),
        }
        for b, sku, code in rows
    ]


# ---------- 库位 ----------


async def list_locations(db: AsyncSession) -> list[WarehouseLocation]:
    """库位全量列表。"""
    return list(
        (await db.execute(select(WarehouseLocation).order_by(WarehouseLocation.code))).scalars()
    )


async def create_location(
    db: AsyncSession, code: str, name: Optional[str], remark: Optional[str]
) -> WarehouseLocation:
    """新建库位：编码唯一冲突 409。"""
    dup = (
        await db.execute(select(WarehouseLocation).where(WarehouseLocation.code == code))
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "库位编码已存在")
    loc = WarehouseLocation(code=code, name=name, remark=remark)
    db.add(loc)
    await db.flush()
    await db.refresh(loc)
    return loc


# ---------- 盘点 ----------


async def create_stocktaking(db: AsyncSession, user_id: Optional[str]) -> Stocktaking:
    """创建盘点单：对所有商品生成账面数量快照（system_qty）。"""
    products = list((await db.execute(select(Product))).scalars())
    st = Stocktaking(status="processing", created_by=user_id)
    db.add(st)
    await db.flush()
    for p in products:
        db.add(StocktakingItem(stocktaking_id=st.id, product_id=p.id, system_qty=p.stock))
    await db.flush()
    # refresh 会使关系变 lazy——用 selectinload 重查一次（避免 async 下 MissingGreenlet）
    return await get_stocktaking_or_404(db, st.id)


async def get_stocktaking_or_404(db: AsyncSession, stocktaking_id: str) -> Stocktaking:
    """取盘点单（预加载明细 + 商品信息）。"""
    st = (
        await db.execute(
            select(Stocktaking)
            .where(Stocktaking.id == stocktaking_id)
            .options(selectinload(Stocktaking.items))
        )
    ).scalar_one_or_none()
    if st is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "盘点单不存在")
    return st


async def update_counted_qty(
    db: AsyncSession, stocktaking_id: str, item_id: str, counted_qty: int
) -> StocktakingItem:
    """录入实盘数（仅 processing 状态可录入）。"""
    st = await get_stocktaking_or_404(db, stocktaking_id)
    if st.status != "processing":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "盘点单已提交，不可再录入")
    item = await db.get(StocktakingItem, item_id)
    if item is None or item.stocktaking_id != stocktaking_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "盘点明细不存在")
    item.counted_qty = counted_qty
    await db.flush()
    return item


async def complete_stocktaking(
    db: AsyncSession, stocktaking_id: str, user_id: Optional[str]
) -> Stocktaking:
    """提交盘点：差异按 check 流水入账 + 修正最新批次剩余量。

    - 差异 = 0 或未录入的项跳过
    - apply_inventory_op(type=check) 把余额调整为实盘数（账实分离）
    - 批次修正：差异一次性记到该商品最近创建的批次（简版策略，P1 可按比例分摊）
    """
    st = await get_stocktaking_or_404(db, stocktaking_id)
    if st.status != "processing":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "盘点单已提交")

    adjusted = 0
    for item in st.items:
        if item.counted_qty is None or item.counted_qty == item.system_qty:
            continue
        diff = item.counted_qty - item.system_qty  # 正=盘盈，负=盘亏
        await apply_inventory_op(
            db,
            InventoryOpCreate(
                product_id=item.product_id,
                type="check",
                quantity=item.counted_qty,
                reason="盘点差异调整",
            ),
            user_id,
        )
        # 修正最新批次剩余量（盘盈/盘亏同向叠加）
        latest_batch = (
            await db.execute(
                select(Batch)
                .where(Batch.product_id == item.product_id)
                .order_by(Batch.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_batch is not None:
            latest_batch.qty_remaining = max(0, latest_batch.qty_remaining + diff)
        adjusted += 1

    st.status = "completed"
    await db.flush()
    # 返回调整统计（供前端提示）；不 refresh（避免关系过期触发 lazy IO）
    st.__dict__["adjusted_count"] = adjusted
    return st


async def list_stocktakings(db: AsyncSession) -> list[dict]:
    """盘点单列表（附明细数）。"""
    rows = list(
        (
            await db.execute(
                select(Stocktaking).options(selectinload(Stocktaking.items)).order_by(
                    Stocktaking.created_at.desc()
                )
            )
        ).scalars()
    )
    return [
        {
            "id": st.id,
            "status": st.status,
            "remark": st.remark,
            "item_count": len(st.items),
            "created_at": st.created_at.isoformat(),
        }
        for st in rows
    ]
