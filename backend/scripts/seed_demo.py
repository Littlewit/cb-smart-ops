r"""演示数据填充：让各页面有完整、好看的业务数据（幂等，可重复执行）。

前置：Mock 平台服务需运行在 8001（商品同步与订单拉取走真实 HTTP）。
执行（backend 目录下）：.venv\\Scripts\\python.exe scripts\\seed_demo.py

覆盖页面：
- 商品/库存看板：3 平台 6 商品（含 2 个预警）+ 近 7 天出入库流水
- 订单管理：~10 单（已发货/待发货/待拆单三种状态）+ 发货单
- 报表中心：30 天销售趋势（已发货订单金额分布）、发货时效、财务对账
- AI 助手：补货/定价建议各若干（真实 Chain 产出）
- 采购/仓库：供应商 + 已完成采购单（批次入库）
"""

import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.ai import chains  # noqa: E402
from app.core.database import task_session  # noqa: E402
from app.models import (  # noqa: E402
    AiSuggestion,
    Order,
    Product,
    Shipment,
    Shop,
    User,
)
from app.schemas import InventoryOpCreate  # noqa: E402
from app.schemas.purchase import (  # noqa: E402
    PurchaseOrderCreate,
    PurchaseOrderItemIn,
    ReceiveItemIn,
    ReceiveRequest,
    SupplierCreate,
)
from app.services import (  # noqa: E402
    inventory_service,
    order_service,
    purchase_service,
)
from app.tasks.sync import _sync_shop  # noqa: E402


async def ensure_shops(db) -> list[Shop]:
    """三家店铺：mock / shein / shopify（幂等）。"""
    wanted = [
        ("mock", "冒烟店铺"),
        ("shein", "SHEIN 旗舰店"),
        ("shopify", "Shopify 独立站"),
    ]
    shops = []
    for platform, name in wanted:
        shop = (
            await db.execute(select(Shop).where(Shop.name == name))
        ).scalar_one_or_none()
        if shop is None:
            shop = Shop(platform=platform, name=name, status="active")
            db.add(shop)
            await db.flush()
            print(f"+ 店铺: {name}")
        shops.append(shop)
    return shops


def beautify_alerts(db, products: list[Product]) -> None:
    """预警美化：确保 MOCK-002/SH-1002 处于预警（好看的红行 + 驱动 AI 建议）。"""
    from app.models import InventoryLog

    for sku, target in (("MOCK-002", 6), ("SH-1002", 4)):
        p = next((x for x in products if x.sku == sku), None)
        if p is None or p.stock == target:
            continue
        before = p.stock
        p.stock = target
        p.alert_status = target < p.safety_stock
        db.add(
            InventoryLog(
                product_id=p.id,
                type="check",
                quantity=target,
                stock_before=before,
                stock_after=target,
                reason="演示数据：模拟平台库存下降",
            )
        )
        print(f"~ 预警商品: {sku} {before}→{target}")


async def seed_flows(db, products: list[Product], user_id: str) -> None:
    """近 7 天出入库流水：让库存看板的流水抽屉有时间分布。"""
    plans = [
        ("MOCK-001", "in", 20, "采购入库（演示）"),
        ("MOCK-003", "out", 10, "促销出库（演示）"),
        ("SP-2001", "out", 3, "订单发货（演示）"),
    ]
    now = datetime.now()
    for sku, typ, qty, reason in plans:
        p = next((x for x in products if x.sku == sku), None)
        if p is None:
            continue
        try:
            log = await inventory_service.apply_inventory_op(
                db,
                InventoryOpCreate(product_id=p.id, type=typ, quantity=qty, reason=reason),
                user_id,
            )
            # 流水时间散布到近 7 天（created_at 本为服务端默认值，这里手动覆盖）
            log.created_at = now - timedelta(days=random.uniform(1, 6))
        except Exception as exc:
            print(f"! 流水跳过 {sku} {typ}: {exc}")


async def spread_order_times(db) -> None:
    """订单时间分布：已发货单散布近 2 天（发货时效好看），未发货单散布近 28 天（趋势图有数据）。"""
    now = datetime.now()
    for order in (await db.execute(select(Order))).scalars():
        if order.status == "shipped":
            delta = timedelta(hours=random.uniform(6, 48))
        else:
            delta = timedelta(days=random.uniform(2, 28))
        order.created_at = now - delta


async def seed_suggestions(db, products: list[Product]) -> None:
    """AI 建议：对预警/常量商品跑真实 Chain 并落库（AI 不可用自动走规则引擎）。"""
    existing = len(list((await db.execute(select(AiSuggestion.id))).scalars()))
    if existing >= 3:
        print(f"AI 建议已有 {existing} 条，跳过")
        return
    targets = [
        (next((x for x in products if x.sku == "MOCK-002"), None), "restock"),
        (next((x for x in products if x.sku == "SH-1002"), None), "restock"),
        (next((x for x in products if x.sku == "MOCK-001"), None), "pricing"),
    ]
    for product, typ in targets:
        if product is None:
            continue
        if typ == "restock":
            outcome = await chains.restock_chain(db, product)
        else:
            outcome = await chains.pricing_chain(db, product)
        db.add(
            AiSuggestion(
                type=typ,
                product_id=product.id,
                content=outcome["content"],
                rule_refs=outcome["rule_refs"],
                status="pending",
            )
        )
        print(f"+ AI 建议: {product.sku} {typ} source={outcome['source']}")


async def seed_purchase(db, products: list[Product], user_id: str) -> None:
    """采购闭环：供应商 + 预警商品采购单（已完成，含批次入库）。"""
    from app.models import PurchaseOrder

    if (await db.execute(select(PurchaseOrder.id).limit(1))).scalar_one_or_none():
        print("采购单已存在，跳过采购演示数据")
        return

    supplier = await purchase_service.create_supplier(
        db,
        SupplierCreate(
            name="深圳华强电子有限公司",
            contact="陈经理",
            phone="13800138000",
            email="chen@huqiang-demo.com",
        ),
    )
    print(f"+ 供应商: {supplier.name}")

    po_by = {p.sku: p for p in products}
    items = [
        PurchaseOrderItemIn(product_id=p.id, quantity=qty, unit_price=price)
        for p, qty, price in (
            (po_by["MOCK-002"], 40, 6.5),
            (po_by["SH-1002"], 30, 16.0),
        )
        if p is not None
    ]
    if not items:
        return

    po = await purchase_service.create_po(
        db,
        PurchaseOrderCreate(
            supplier_id=supplier.id, remark="Agent 补货计划转采购单（演示）", items=items
        ),
        user_id,
    )
    await purchase_service.submit_po(db, po.id)
    print(f"+ 采购单: {po.po_no} 已提交")

    # 全量收货（生成批次 + in 流水 + 库存上升 → 预警解除）
    po_full = await purchase_service.get_po_detail(db, po.id)
    lines = [
        ReceiveItemIn(item_id=it["id"], quantity=it["quantity"])
        for it in po_full["items"]
    ]
    await purchase_service.receive_po(db, po.id, ReceiveRequest(items=lines), user_id)
    print(f"+ 收货完成: {po.po_no}（批次生成，预警应解除）")


async def main() -> None:
    # 前置检查：Mock 平台可达（同步/拉单走真实 HTTP）
    import httpx

    try:
        httpx.get("http://127.0.0.1:8001/docs", timeout=3)
    except Exception:
        print("!! Mock 平台未运行（8001），请先执行：")
        print("   backend\\.venv\\Scripts\\uvicorn mock_platform.main:app --port 8001")
        return

    # 分段短事务：每段独立 task_session 并及时提交——
    # SQLite 写锁是库级的，长事务未提交时再开第二个连接写库必然 locked
    async with task_session() as db:
        user = (
            await db.execute(select(User).where(User.username == "smoke_admin"))
        ).scalar_one()
        user_id = user.id
        shops = await ensure_shops(db)

    # 2) 商品同步（每店独立短事务，内部自管连接）
    for shop in shops:
        result = await _sync_shop(shop.id)
        print(f"~ 同步 {shop.name}: 新增 {result.get('created', 0)}，更新 {result.get('updated', 0)}")

    # 3) 预警美化 + 近 7 天流水
    async with task_session() as db:
        products = list((await db.execute(select(Product))).scalars())
        print(f"商品总数: {len(products)}")
        beautify_alerts(db, products)
        await seed_flows(db, products, user_id)

    # 4) 订单：拉单 → 时间分布 → 拆单 → 发一半（留 2 张待发货）
    async with task_session() as db:
        for shop in shops:
            for _ in range(3):
                r = await order_service.fetch_orders(db, shop.id, limit=3, user_id=user_id)
                print(f"~ 拉单 {shop.name}: +{r['fetched']}（跳过 {r['skipped']}）")
        await spread_order_times(db)
        r = await order_service.split_orders(db, None, user_id)
        print(f"~ 拆单结果: {r}")

    async with task_session() as db:
        waiting = list(
            (await db.execute(select(Shipment).where(Shipment.status == "waiting"))).scalars()
        )
        shipped = 0
        for i, sp in enumerate(waiting):
            if i >= max(0, len(waiting) - 2):
                break  # 留最后 2 张待发货
            try:
                await order_service.ship_shipment(
                    db, sp.id, f"SF{2000000 + i}", "顺丰速运", user_id
                )
                shipped += 1
            except Exception as exc:
                # 库存不足属正常业务边界（多单引用同一商品），跳过该单
                await db.rollback()
                print(f"! 发货跳过: {exc}")
        print(f"~ 发货: 成功 {shipped} / 待发 {len(waiting) - shipped}")

    # 5) AI 建议 + 采购闭环
    async with task_session() as db:
        products = list((await db.execute(select(Product))).scalars())
        await seed_suggestions(db, products)

    async with task_session() as db:
        products = list((await db.execute(select(Product))).scalars())
        await seed_purchase(db, products, user_id)


if __name__ == "__main__":
    asyncio.run(main())
