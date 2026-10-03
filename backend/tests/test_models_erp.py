"""ERP 扩展模型测试：采购/仓库/发货的新表约束与关系。

沿用 test_models.py 的裸 async 模式（asyncio_mode=auto + tmp_path 独立库）。
重点验证：
- 唯一约束（供应商名/采购单号/批次号）防重复主数据
- 采购单级联删除明细（草稿清理场景）
- Order 新列默认值（legacy 数据兼容语义）
- PurchaseOrderItem.pending_qty / StocktakingItem.diff_qty 计算属性
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.models import (
    Batch,
    Order,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Shipment,
    ShipmentItem,
    Shop,
    Stocktaking,
    StocktakingItem,
    Supplier,
    WarehouseLocation,
)


async def seed_shop_product(s):
    """建店铺+商品（product_id 非空约束需要真实商品行）。"""
    shop = Shop(platform="mock", name="测试店铺")
    s.add(shop)
    await s.flush()
    product = Product(shop_id=shop.id, sku="A001", name="测试商品", stock=10, safety_stock=5)
    s.add(product)
    await s.flush()
    return shop, product


async def make_session(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/erp.db", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_supplier_name_unique(tmp_path):
    """供应商名唯一约束：重名插入应报 IntegrityError。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        s.add(Supplier(name="华南电子厂"))
        await s.flush()
        s.add(Supplier(name="华南电子厂"))
        try:
            await s.flush()
            raised = False
        except IntegrityError:
            raised = True
        assert raised
    await engine.dispose()


async def test_purchase_order_cascade_items(tmp_path):
    """采购单级联删除明细；pending_qty 计算正确。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        sup = Supplier(name="测试供应商")
        s.add(sup)
        await s.flush()
        _, product = await seed_shop_product(s)
        po = PurchaseOrder(po_no="PO-TEST-0001", supplier_id=sup.id, status="draft",
                           total_amount=100.0)
        s.add(po)
        await s.flush()
        item = PurchaseOrderItem(
            purchase_order_id=po.id, product_id=product.id, quantity=10, unit_price=10.0,
            received_qty=4,
        )
        s.add(item)
        await s.flush()

        assert item.pending_qty == 6  # 10 - 4

        # 级联删除：删采购单后明细应被 ORM 级联清除
        await s.delete(po)
        await s.flush()
        remaining = (
            await s.execute(
                select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po.id)
            )
        ).scalars().all()
        assert remaining == []
    await engine.dispose()


async def test_batch_no_unique_and_location(tmp_path):
    """批次号唯一；批次可关联库位（可空）。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        loc = WarehouseLocation(code="A-01-01", name="A 区 1 排 1 层")
        s.add(loc)
        await s.flush()
        # product_id 非空约束——建一个真实商品再挂批次
        s.add(Batch(batch_no="B-TEST-0001", product_id="p-x", qty_initial=5, qty_remaining=5,
                    location_id=loc.id))
        await s.flush()
        s.add(Batch(batch_no="B-TEST-0001", product_id="p-x", qty_initial=1, qty_remaining=1))
        try:
            await s.flush()
            raised = False
        except IntegrityError:
            raised = True
        assert raised
    await engine.dispose()


async def test_stocktaking_diff_property(tmp_path):
    """盘点差异计算属性：盘盈/盘亏/未录入三种状态。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        st = Stocktaking(status="processing")
        s.add(st)
        await s.flush()
        _, product = await seed_shop_product(s)
        items = [
            StocktakingItem(stocktaking_id=st.id, product_id=product.id, system_qty=10, counted_qty=12),  # 盘盈 +2
            StocktakingItem(stocktaking_id=st.id, product_id=product.id, system_qty=10, counted_qty=8),   # 盘亏 -2
            StocktakingItem(stocktaking_id=st.id, product_id=product.id, system_qty=10),                  # 未录入
        ]
        s.add_all(items)
        await s.flush()

        assert items[0].diff_qty == 2
        assert items[1].diff_qty == -2
        assert items[2].diff_qty is None
    await engine.dispose()


async def test_order_new_columns_defaults(tmp_path):
    """Order 新列带默认值：legacy 数据兼容（旧代码只写 4 字段）。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        o = Order(shop_id="shop-x", platform_order_no="NO-1", amount=9.9)
        s.add(o)
        await s.flush()

        assert o.status == "pending"
        assert o.platform is None
        assert o.receiver_name is None
        assert o.shipped_at is None
    await engine.dispose()


async def test_shipment_cascade_items(tmp_path):
    """发货单级联删除明细。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        shop = Shop(platform="mock", name="发货测试店铺")
        s.add(shop)
        await s.flush()
        order = Order(shop_id=shop.id, platform_order_no="NO-SHIP-1", amount=10.0)
        s.add(order)
        await s.flush()
        _, product = await seed_shop_product(s)
        sh = Shipment(order_id=order.id, status="waiting")
        s.add(sh)
        await s.flush()
        s.add(ShipmentItem(shipment_id=sh.id, product_id=product.id, quantity=3))
        s.add(sh)
        await s.flush()
        s.add(ShipmentItem(shipment_id=sh.id, product_id="p1", quantity=3))
        await s.flush()

        await s.delete(sh)
        await s.flush()
        remaining = (
            await s.execute(select(ShipmentItem).where(ShipmentItem.shipment_id == sh.id))
        ).scalars().all()
        assert remaining == []
    await engine.dispose()
