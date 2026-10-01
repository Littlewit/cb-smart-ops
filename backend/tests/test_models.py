import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.models import InventoryLog, Product, Shop


async def make_session(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/t.db", poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_inventory_flow_consistency(tmp_path):
    """账实分离：流水与余额同事务更新，低库存自动标记预警。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        shop = Shop(platform="mock", name="测试店铺")
        s.add(shop)
        await s.flush()
        product = Product(shop_id=shop.id, sku="A001", name="测试商品", stock=10, safety_stock=20)
        s.add(product)
        await s.flush()

        # 出库 5 件：写流水 + 更新余额（业务层同事务）
        s.add(
            InventoryLog(
                product_id=product.id,
                type="out",
                quantity=5,
                stock_before=10,
                stock_after=5,
                reason="测试出库",
            )
        )
        product.stock = 5
        product.alert_status = product.stock < product.safety_stock
        await s.commit()

        loaded = (await s.execute(select(Product))).scalar_one()
        assert loaded.stock == 5
        assert loaded.alert_status is True
    await engine.dispose()


async def test_shop_unique_constraint(tmp_path):
    """同平台店铺名唯一。"""
    engine, Session = await make_session(tmp_path)
    async with Session() as s:
        s.add(Shop(platform="mock", name="重复店铺"))
        await s.commit()
        s.add(Shop(platform="mock", name="重复店铺"))
        with pytest.raises(IntegrityError):
            await s.commit()
    await engine.dispose()
