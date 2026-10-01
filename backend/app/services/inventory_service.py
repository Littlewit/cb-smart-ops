"""库存业务：入库/出库/盘点（账实分离）+ 概览统计。

核心约束（需求 FR-2.1 / 系统设计 §3）：
库存流水（inventory_logs）与余额（products.stock）在同一事务内更新，
保证任何时刻"流水推演出的余额 = 实际余额"。
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InventoryLog, Product, Shop
from app.schemas import InventoryOpCreate

# 流水类型 -> 操作说明（用于 reason 自动生成）
_TYPE_LABELS = {"in": "入库", "out": "出库", "check": "盘点"}


async def apply_inventory_op(
    db: AsyncSession, payload: InventoryOpCreate, operator_id: str | None
) -> InventoryLog:
    """执行一次库存变动：更新余额 + 写流水（同事务）。

    返回生成的流水记录；库存不足（out）时抛 400 且不产生任何变更。
    """
    product = await db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "商品不存在")

    stock_before = product.stock
    if payload.type == "in":
        stock_after = stock_before + payload.quantity
    elif payload.type == "out":
        if payload.quantity > stock_before:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"库存不足：当前 {stock_before}，尝试出库 {payload.quantity}",
            )
        stock_after = stock_before - payload.quantity
    else:  # check：quantity 为实盘数量
        stock_after = payload.quantity

    # 同事务内更新余额、刷新预警状态、写入流水
    product.stock = stock_after
    product.alert_status = stock_after < product.safety_stock

    log = InventoryLog(
        product_id=product.id,
        type=payload.type,
        quantity=payload.quantity,
        stock_before=stock_before,
        stock_after=stock_after,
        reason=payload.reason or _TYPE_LABELS[payload.type],
        operator_id=operator_id,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def list_logs(
    db: AsyncSession, product_id: str | None, page: int, page_size: int
) -> tuple[list[InventoryLog], int]:
    """库存流水分页列表（可按商品过滤），返回 (items, total)。"""
    query = select(InventoryLog).order_by(InventoryLog.created_at.desc())
    count_query = select(func.count(InventoryLog.id))
    if product_id is not None:
        query = query.where(InventoryLog.product_id == product_id)
        count_query = count_query.where(InventoryLog.product_id == product_id)

    total = (await db.execute(count_query)).scalar_one()
    items = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
        .all()
    )
    return items, total


async def summary(db: AsyncSession) -> dict:
    """库存概览：商品总数 / 预警数 / 店铺数 / 预警商品列表（看板数据源）。"""
    total_products = (
        await db.execute(select(func.count(Product.id)))
    ).scalar_one()
    alert_count = (
        await db.execute(select(func.count(Product.id)).where(Product.alert_status.is_(True)))
    ).scalar_one()
    total_shops = (await db.execute(select(func.count(Shop.id)))).scalar_one()
    alert_products = list(
        (
            await db.execute(
                select(Product)
                .where(Product.alert_status.is_(True))
                .order_by(Product.stock.asc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    return {
        "total_products": total_products,
        "alert_count": alert_count,
        "total_shops": total_shops,
        "alert_products": alert_products,
    }
