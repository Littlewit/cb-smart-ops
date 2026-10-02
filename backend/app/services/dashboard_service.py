"""数据看板业务：核心指标 / 近7天销售趋势 / 店铺商品分布。

数据全部来自聚合查询（orders/products/shops），不做复杂 OLAP。
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Product, Shop


async def stats(db: AsyncSession, days: int = 7) -> dict:
    """看板统计数据（对应前端 Dashboard.vue 的三种图/卡片）。

    days：销售趋势天数（7/30），由前端筛选 pill 传入。
    """
    # ---------- 指标卡片 ----------
    total_products = (await db.execute(select(func.count(Product.id)))).scalar_one()
    alert_count = (
        await db.execute(select(func.count(Product.id)).where(Product.alert_status.is_(True)))
    ).scalar_one()
    total_shops = (await db.execute(select(func.count(Shop.id)))).scalar_one()

    # ---------- 近 N 天销售趋势 ----------
    since = datetime.now() - timedelta(days=days)
    # func.date() 双方言兼容：SQLite date(ts) 与 PG date(timestamp) 均返回 YYYY-MM-DD
    # （不能用 substr(timestamp)：PG 的 substr 不接受 timestamp 类型）
    rows = (
        await db.execute(
            select(
                func.date(Order.created_at).label("date"),
                func.coalesce(func.sum(Order.amount), 0).label("amount"),
            )
            .where(Order.created_at >= since)
            .group_by(func.date(Order.created_at))
            .order_by(func.date(Order.created_at))
        )
    ).all()
    # 补齐 N 天连续日期（无订单的天填 0，保证折线不断）
    amount_by_date = {r.date: float(r.amount) for r in rows}
    sales_trend = []
    for i in range(days - 1, -1, -1):
        day = datetime.now() - timedelta(days=i)
        key = day.strftime("%Y-%m-%d")
        sales_trend.append({"date": key[5:], "amount": amount_by_date.get(key, 0.0)})

    # ---------- 店铺商品分布 ----------
    dist_rows = (
        await db.execute(
            select(Shop.name, func.count(Product.id))
            .join(Product, Product.shop_id == Shop.id, isouter=True)
            .group_by(Shop.id)
            .order_by(Shop.created_at)
        )
    ).all()
    shop_distribution = [{"shop": name, "product_count": count} for name, count in dist_rows]

    return {
        "total_products": total_products,
        "alert_count": alert_count,
        "total_shops": total_shops,
        "sales_trend": sales_trend,
        "shop_distribution": shop_distribution,
    }
