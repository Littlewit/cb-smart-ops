"""同步与预警任务：拉取平台商品 → upsert（幂等）→ 差异写流水 → 刷新预警。

幂等性约定（系统设计 §10）：同一店铺重复同步，商品数不变；
仅当库存发生变化时才写 inventory_log（type=check，reason=平台同步）。
"""

import asyncio
from datetime import datetime

from sqlalchemy import select, update

from app.core.database import task_session
from app.models import InventoryLog, Product, Shop
from app.tasks.celery_app import celery_app
from app.utils import platform_client


@celery_app.task(
    name="app.tasks.sync.sync_shop_task",
    # 失败自动重试 1 次（指数退避），平台接口抖动时不丢数据
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=1,
)
def sync_shop_task(shop_id: str) -> dict:
    """同步单个店铺：入口为同步函数（Celery 要求），内部用 asyncio.run 跑异步逻辑。"""
    return asyncio.run(_sync_shop(shop_id))


async def _sync_shop(shop_id: str) -> dict:
    """同步逻辑本体：拉取 → 逐 SKU upsert → 差异写流水 → 刷新预警。"""
    async with task_session() as session:
        shop = await session.get(Shop, shop_id)
        if shop is None:
            return {"error": "shop not found", "created": 0, "updated": 0}

        # 平台调用是同步 HTTP，丢到线程执行避免阻塞事件循环
        items = await asyncio.to_thread(platform_client.fetch_products, shop.platform)

        created = updated = 0
        for item in items:
            product = (
                await session.execute(
                    select(Product).where(
                        Product.shop_id == shop_id, Product.sku == item["sku"]
                    )
                )
            ).scalar_one_or_none()

            if product is None:
                # 新商品：直接按平台数据建，预警状态一并初始化
                product = Product(
                    shop_id=shop_id,
                    sku=item["sku"],
                    name=item.get("name", item["sku"]),
                    cost_price=item.get("cost_price", 0.0),
                    sale_price=item.get("sale_price", 0.0),
                    stock=item["stock"],
                    safety_stock=item.get("safety_stock", 10),
                    alert_status=item["stock"] < item.get("safety_stock", 10),
                )
                session.add(product)
                created += 1
            else:
                # 已存在：仅当库存变化时更新余额并写"盘点"流水（幂等的关键）
                if product.stock != item["stock"]:
                    session.add(
                        InventoryLog(
                            product_id=product.id,
                            type="check",
                            quantity=item["stock"],
                            stock_before=product.stock,
                            stock_after=item["stock"],
                            reason="平台同步",
                            operator_id=None,  # 系统自动操作
                        )
                    )
                    product.stock = item["stock"]
                    product.alert_status = product.stock < product.safety_stock
                    updated += 1
                # 名称/售价跟进平台（库存未变时不计 updated）
                product.name = item.get("name", product.name)
                product.sale_price = item.get("sale_price", product.sale_price)

        await session.flush()
        return {"shop_id": shop_id, "created": created, "updated": updated}


@celery_app.task(name="app.tasks.sync.sync_all_shops_task")
def sync_all_shops_task() -> list:
    """遍历所有 active 店铺逐个同步（演示规模下串行即可，无需 fan-out）。"""
    async def _run() -> list:
        async with task_session() as session:
            shops = (
                await session.execute(select(Shop).where(Shop.status == "active"))
            ).scalars().all()
            return [s.id for s in shops]

    shop_ids = asyncio.run(_run())
    return [sync_shop_task(sid) for sid in shop_ids]


@celery_app.task(name="app.tasks.sync.scan_alerts_task")
def scan_alerts_task() -> dict:
    """全量刷新预警状态：alert_status = (stock < safety_stock)，单条 SQL 完成。"""
    async def _run() -> dict:
        async with task_session() as session:
            result = await session.execute(
                update(Product).values(alert_status=Product.stock < Product.safety_stock)
            )
            return {"refreshed": result.rowcount}

    # updated_at 手动刷新（UPDATE 语句不走 ORM onupdate）
    async def _touch() -> None:
        async with task_session() as session:
            await session.execute(
                update(Product).values(updated_at=datetime.now())
            )

    result = asyncio.run(_run())
    asyncio.run(_touch())
    return result
