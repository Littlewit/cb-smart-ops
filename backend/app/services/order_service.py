"""订单业务：多平台拉单（幂等）→ 拆单（按库存充足性）→ 发货流转（扣库存）。

状态机：pending（已拉取待拆）→ partial（已建发货单待发）→ shipped（全部发货）。
拆单规则（演示级收敛）：订单内全部商品项库存充足才建发货单；任一不足
则订单保持 pending（等采购入库后再次拆单），库存预警由账实分离体系负责。
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, Product, Shipment, ShipmentItem, Shop
from app.schemas.inventory import InventoryOpCreate
from app.services.inventory_service import apply_inventory_op
from app.utils.platform_client import fetch_platform_orders


# ---------- 拉单 ----------


async def fetch_orders(
    db: AsyncSession, shop_id: str, limit: int, user_id: Optional[str]
) -> dict:
    """从平台拉取订单并落库（幂等）。

    - (shop_id, platform_order_no) 唯一索引兜底：重复拉取已入库订单直接跳过
    - 订单项按 (shop_id, platform_sku) 匹配本地商品；某项匹配不到则丢弃该项，
      整单所有项都匹配不到则跳过整单（避免无法发货的空单）
    """
    shop = await db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "店铺不存在")
    platform = shop.platform

    remote_orders = await fetch_platform_orders(platform, limit=limit)
    fetched, skipped = 0, 0
    for ro in remote_orders:
        no = ro["platform_order_no"]
        # 幂等检查：该店铺下此平台单号已存在则跳过
        dup = (
            await db.execute(
                select(Order.id).where(
                    Order.shop_id == shop_id, Order.platform_order_no == no
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            skipped += 1
            continue

        # 平台 SKU → 本地商品映射
        matched = []
        for it in ro.get("items", []):
            product = (
                await db.execute(
                    select(Product).where(
                        Product.shop_id == shop_id, Product.sku == it["sku"]
                    )
                )
            ).scalar_one_or_none()
            if product is not None:
                matched.append((product, it))
        if not matched:
            skipped += 1
            continue

        order = Order(
            shop_id=shop_id,
            platform_order_no=no,
            status="pending",
            platform=platform,
            amount=round(sum(p.sale_price * it["quantity"] for p, it in matched), 2),
            receiver_name=ro.get("receiver_name"),
            receiver_phone=ro.get("receiver_phone"),
            receiver_address=ro.get("receiver_address"),
        )
        db.add(order)
        await db.flush()
        for product, it in matched:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    platform_sku=it["sku"],
                    quantity=it["quantity"],
                    price=it["price"],
                )
            )
        fetched += 1
    await db.flush()
    return {"fetched": fetched, "skipped": skipped, "shop": shop.name}


# ---------- 拆单 ----------


async def split_orders(
    db: AsyncSession, order_id: Optional[str], user_id: Optional[str]
) -> dict:
    """一键拆单：pending 订单按库存充足性二分。

    全部商品项库存充足 → 生成一个 waiting 发货单（不扣库存，发货时扣），
    订单进入 partial（已拆待发）；任一不足 → 跳过（保持 pending）。
    """
    if order_id:
        rows = (
            await db.execute(
                select(Order)
                .where(Order.id == order_id, Order.status == "pending")
                .options(selectinload(Order.items))
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "订单不存在或不是待拆单状态")
    else:
        rows = list(
            (
                await db.execute(
                    select(Order)
                    .where(Order.status == "pending")
                    .options(selectinload(Order.items))
                    .order_by(Order.created_at)
                    .limit(100)
                )
            ).scalars()
        )

    split_count, skipped = 0, 0
    for order in rows:
        # 逐项检查库存充足性（先全量校验，再建发货单）
        shortages = []
        for item in order.items:
            product = await db.get(Product, item.product_id)
            if product is None or product.stock < item.quantity:
                shortages.append(item.platform_sku)
        if shortages:
            skipped += 1
            continue

        shipment = Shipment(order_id=order.id, status="waiting")
        db.add(shipment)
        await db.flush()
        for item in order.items:
            db.add(
                ShipmentItem(
                    shipment_id=shipment.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
            )
        order.status = "partial"  # 已拆待发
        split_count += 1
    await db.flush()
    return {"split": split_count, "skipped": skipped}


# ---------- 发货 ----------


async def ship_shipment(
    db: AsyncSession, shipment_id: str, tracking_no: str, carrier: Optional[str],
    user_id: Optional[str],
) -> Shipment:
    """发货：扣减库存（账实分离）+ 更新发货单与订单状态。

    先全量校验库存再执行（任一项不足 400，整体不产生变更）；
    订单下全部发货单发完 → 订单 shipped + shipped_at（发货时效统计口径）。
    """
    shipment = (
        await db.execute(
            select(Shipment)
            .where(Shipment.id == shipment_id)
            .options(selectinload(Shipment.items))
        )
    ).scalar_one_or_none()
    if shipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "发货单不存在")
    if shipment.status != "waiting":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"发货单已发货（{shipment.status}）")

    # 预检库存（避免中途不足导致复杂回滚语义）
    for item in shipment.items:
        product = await db.get(Product, item.product_id)
        if product is None or product.stock < item.quantity:
            sku = product.sku if product else item.product_id
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"库存不足：{sku} 需要 {item.quantity}，当前 {product.stock if product else 0}",
            )

    # 逐项扣减（out 流水 + 余额，同事务）
    for item in shipment.items:
        await apply_inventory_op(
            db,
            InventoryOpCreate(
                product_id=item.product_id,
                type="out",
                quantity=item.quantity,
                reason=f"订单发货 {shipment.order_id[:8]}",
            ),
            user_id,
        )

    shipment.status = "shipped"
    shipment.tracking_no = tracking_no
    shipment.carrier = carrier
    shipped_at = datetime.now().isoformat(timespec="seconds")
    shipment.shipped_at = shipped_at

    # 订单下全部发货单已发货 → 订单完成
    all_shipped = all(
        s.status == "shipped"
        for s in (
            await db.execute(
                select(Shipment).where(Shipment.order_id == shipment.order_id)
            )
        ).scalars()
    )
    if all_shipped:
        order = await db.get(Order, shipment.order_id)
        if order is not None:
            order.status = "shipped"
            order.shipped_at = shipped_at
    await db.flush()
    await db.refresh(shipment)
    return shipment


# ---------- 查询 ----------


async def list_orders(
    db: AsyncSession, status_filter: Optional[str], page: int, page_size: int
) -> tuple[list[Order], int]:
    """订单分页列表：默认排除 legacy（历史演示数据）。"""
    query = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    count_query = select(func.count(Order.id))
    if status_filter:
        query, count_query = query.where(Order.status == status_filter), (
            count_query.where(Order.status == status_filter)
        )
    else:
        query, count_query = query.where(Order.status != "legacy"), (
            count_query.where(Order.status != "legacy")
        )
    total = (await db.execute(count_query)).scalar_one()
    items = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
    )
    return items, total


async def list_shipments(
    db: AsyncSession, status_filter: Optional[str], page: int, page_size: int
) -> tuple[list[tuple[Shipment, str]], int]:
    """发货单分页列表（附订单号便于展示）。"""
    query = (
        select(Shipment, Order.platform_order_no)
        .join(Order, Shipment.order_id == Order.id)
        .options(selectinload(Shipment.items))
        .order_by(Shipment.created_at.desc())
    )
    count_query = select(func.count(Shipment.id))
    if status_filter:
        query, count_query = query.where(Shipment.status == status_filter), (
            count_query.where(Shipment.status == status_filter)
        )
    total = (await db.execute(count_query)).scalar_one()
    rows = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).all()
    )
    return rows, total
