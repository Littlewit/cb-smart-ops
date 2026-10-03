"""演示数据种子脚本：让看板/AI 对话在演示时有"真实丰满"的数据。

生成内容（幂等：orders 表已有数据则整体跳过，避免重复堆积）：
- 3 家店铺：华南旗舰店(Mock) / 欧美站(SHEIN) / 东南亚站(Shopify)
- 每店 10 个商品（共 30 个），含 2~3 个低库存预警品
- 每商品 1 条期初入库流水
- 近 30 天约 120+ 笔订单（每店每天 1~4 笔，金额随机）

执行（backend 目录下）：
    .venv\\Scripts\\python.exe scripts\\seed_demo_data.py
"""

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 直接以脚本运行时把 backend 根加入导入路径（与 seed_rules.py 同款处理）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import task_session  # noqa: E402
from app.models import InventoryLog, Order, Product, Shop  # noqa: E402

# ---------- 店铺定义：(平台, 店铺名, SKU前缀) ----------
SHOPS = [
    ("mock", "华南旗舰店", "MOCK"),
    ("shein", "欧美站", "SH"),
    ("shopify", "东南亚站", "SP"),
]

# ---------- 商品池：(名称, 成本价, 售价)，每店按前缀生成 SKU ----------
PRODUCT_POOL = [
    ("无线蓝牙耳机 Pro", 35.0, 89.0),
    ("手机支架（铝合金）", 8.5, 25.9),
    ("USB-C 快充数据线 2m", 4.2, 12.9),
    ("便携蓝牙音箱", 42.0, 129.0),
    ("智能手表表带（硅胶）", 3.8, 15.9),
    ("车载磁吸手机架", 9.6, 35.0),
    ("降噪耳机收纳包", 6.4, 22.0),
    ("迷你充电宝 5000mAh", 28.0, 69.0),
    ("桌面无线充电板", 19.5, 59.0),
    ("防摔手机壳（透明）", 2.9, 13.9),
    ("夏季冰丝防晒袖套", 2.1, 9.9),
    ("折叠收纳箱 30L", 12.0, 39.9),
    ("厨房硅胶铲勺 5件套", 8.8, 29.9),
    ("不锈钢保温杯 500ml", 11.5, 45.0),
    ("宠物自动喂食器", 65.0, 199.0),
    ("瑜伽垫 TPE 8mm", 18.0, 65.0),
    ("LED 化妆镜灯", 14.0, 49.9),
    ("蓝牙自拍杆三脚架", 7.6, 26.9),
    ("儿童益智拼装积木", 9.9, 36.0),
    ("加绒保暖手套", 4.5, 19.9),
    ("电竞鼠标垫 XXL", 6.8, 24.9),
    ("机械键盘键帽套装", 15.0, 55.0),
    ("桌面理线器套装", 3.2, 11.9),
    ("户外露营灯（充电）", 16.5, 59.0),
    ("硅胶折叠水壶", 5.5, 19.9),
    ("汽车缝隙收纳盒", 4.9, 18.8),
    ("美白牙膏（竹炭）", 1.8, 8.9),
    ("化妆刷 12 支套装", 7.9, 32.0),
    ("浴室置物架（免打孔）", 9.9, 34.9),
    ("懒人沙发（小户型）", 88.0, 299.0),
]

# 强制预警的商品序号（在 30 个商品中的下标）：库存压到安全库存以下，
# 让"库存看板预警 → AI 补货建议"链路在演示时立刻有数据
ALERT_INDICES = {1, 10, 20}


def _random_amount() -> float:
    """单笔订单金额：20~600 之间的两位小数随机值。"""
    return round(random.uniform(20, 600), 2)


async def main() -> None:
    async with task_session() as session:
        # ---------- 幂等检查：orders 表已有数据则跳过 ----------
        order_count = (await session.execute(select(func.count(Order.id)))).scalar_one()
        if order_count > 0:
            print(f"orders 表已有 {order_count} 条记录，跳过演示数据 seed")
            return

        now = datetime.now()
        sku_seq = 0  # 商品池全局序号，用于挑出强制预警品

        for platform, shop_name, sku_prefix in SHOPS:
            # ---------- 店铺 ----------
            shop = Shop(platform=platform, name=shop_name, credentials_enc=None, status="active")
            session.add(shop)
            await session.flush()  # 拿到 shop.id

            # ---------- 商品：每店 10 个 ----------
            for i in range(10):
                name, cost, price = PRODUCT_POOL[sku_seq % len(PRODUCT_POOL)]
                sku = f"{sku_prefix}-{1001 + sku_seq:04d}"
                sku_seq += 1

                safety = random.randint(10, 30)
                if (sku_seq - 1) in ALERT_INDICES:
                    stock = random.randint(0, safety - 1)      # 强制低于安全库存 → 预警
                else:
                    stock = random.randint(safety + 5, 150)    # 正常库存

                product = Product(
                    shop_id=shop.id,
                    sku=sku,
                    name=f"{name}",
                    cost_price=cost,
                    sale_price=price,
                    stock=stock,
                    safety_stock=safety,
                    alert_status=stock < safety,
                )
                session.add(product)
                await session.flush()  # 拿到 product.id

                # 期初入库流水（账实分离：余额与流水成对出现）
                session.add(
                    InventoryLog(
                        product_id=product.id,
                        type="in",
                        quantity=stock,
                        stock_before=0,
                        stock_after=stock,
                        reason="期初入库",
                        operator_id=None,
                    )
                )

            # ---------- 订单：近 30 天，每店每天 1~4 笔 ----------
            for day_offset in range(29, -1, -1):
                day = now - timedelta(days=day_offset)
                date_str = day.strftime("%Y%m%d")
                for seq in range(random.randint(1, 4)):
                    order = Order(
                        shop_id=shop.id,
                        platform_order_no=f"ORD-{sku_prefix}-{date_str}-{seq + 1:03d}",
                        # 演示数据统一标 legacy：订单管理页只展示 ERP 拉单流程的真实订单
                        status="legacy",
                        amount=_random_amount(),
                        created_at=day.replace(
                            hour=random.randint(8, 22),
                            minute=random.randint(0, 59),
                            second=random.randint(0, 59),
                            microsecond=0,
                        ),
                    )
                    session.add(order)

        await session.flush()

        # ---------- 结果汇报 ----------
        shops = (await session.execute(select(func.count(Shop.id)))).scalar_one()
        products = (await session.execute(select(func.count(Product.id)))).scalar_one()
        orders = (await session.execute(select(func.count(Order.id)))).scalar_one()
        alerts = (
            await session.execute(select(func.count(Product.id)).where(Product.alert_status.is_(True)))
        ).scalar_one()
        print(
            f"演示数据已写入：店铺 {shops} 家 / 商品 {products} 个 / "
            f"订单 {orders} 笔 / 预警商品 {alerts} 个"
        )
        print("提示：刷新前端页面即可看到带数据的图表；登录 admin / admin123")


if __name__ == "__main__":
    asyncio.run(main())
