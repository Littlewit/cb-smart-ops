"""报表业务：CEO 看板 / 运营绩效 / 财务对账（纯查询聚合，不建新表）。

口径说明（面试可讲点）：
- 采购应付 = purchase_order_items 数量 × 单价（status ∈ submitted/receiving/completed，
  草稿与已撤销不计入负债）
- 销售应收 = orders.amount（status ∈ shipped/partial/legacy/done，
  legacy 为历史演示数据也计入收入口径；pending 未发货不算应收）
- 毛利 = 订单项 (price − cost_price) × quantity 聚合
- 库存周转（简化）= 近 30 天出库量 / 当前库存量（越大周转越快）
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    InventoryLog,
    Order,
    OrderItem,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Shipment,
    Supplier,
)

# 计入采购应付的采购单状态（草稿/撤销不算负债）
_AP_STATUSES = ("submitted", "receiving", "completed")
# 计入销售应收的订单状态（未发货的 pending 不算应收；legacy 为历史口径）
_AR_STATUSES = ("shipped", "partial", "legacy", "done")


async def ceo_dashboard(db: AsyncSession, days: int = 30) -> dict:
    """CEO 看板：GMV / 毛利 / 库存周转 / 预警数 + 近 N 天销售趋势。

    单次查询聚合完成（不逐商品循环），趋势口径与既有 dashboard.stats
    保持一致（空缺日补 0 保证折线连续）。
    """
    since = datetime.now() - timedelta(days=days)

    # GMV 与毛利：订单项 join 商品取成本价
    gmv_q = (
        select(
            func.coalesce(func.sum(OrderItem.price * OrderItem.quantity), 0.0),
            func.coalesce(
                func.sum(
                    (OrderItem.price - Product.cost_price) * OrderItem.quantity
                ),
                0.0,
            ),
        )
        .join(Product, OrderItem.product_id == Product.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status.in_(_AR_STATUSES), Order.created_at >= since)
    )
    gmv, profit = (await db.execute(gmv_q)).one()

    # 库存现状：总库存量 / 预警数
    total_stock = (
        await db.execute(select(func.coalesce(func.sum(Product.stock), 0)))
    ).scalar_one()
    alert_count = (
        await db.execute(select(func.count(Product.id)).where(Product.alert_status.is_(True)))
    ).scalar_one()

    # 近 N 天出库量（周转分母口径：当前库存）
    out_qty = (
        await db.execute(
            select(func.coalesce(func.sum(InventoryLog.quantity), 0)).where(
                InventoryLog.type == "out", InventoryLog.created_at >= since
            )
        )
    ).scalar_one()
    turnover = round(out_qty / total_stock, 2) if total_stock else 0.0

    # 销售趋势（按日聚合，空缺日由 service 补 0）
    trend_q = (
        select(
            func.date(Order.created_at).label("d"),
            func.coalesce(func.sum(Order.amount), 0.0),
        )
        .where(Order.status.in_(_AR_STATUSES), Order.created_at >= since)
        .group_by("d")
        .order_by("d")
    )
    rows = {str(d): float(v) for d, v in (await db.execute(trend_q)).all()}
    trend = []
    cur = datetime.now() - timedelta(days=days - 1)
    while cur <= datetime.now():
        key = cur.strftime("%Y-%m-%d")
        trend.append({"date": key, "amount": rows.get(key, 0.0)})
        cur += timedelta(days=1)

    return {
        "days": days,
        "gmv": round(float(gmv), 2),
        "gross_profit": round(float(profit), 2),
        "gross_margin": round(float(profit) / float(gmv) * 100, 1) if float(gmv) else 0.0,
        "total_stock": int(total_stock),
        "stock_turnover": turnover,
        "alert_count": alert_count,
        "sales_trend": trend,
    }


async def operation_performance(db: AsyncSession) -> dict:
    """运营绩效：发货时效 / 拉单-发货漏斗 / 预警处理情况。"""
    total_orders = (
        await db.execute(
            select(func.count(Order.id)).where(Order.status != "legacy")
        )
    ).scalar_one()
    shipped_orders = (
        await db.execute(
            select(func.count(Order.id)).where(Order.status == "shipped")
        )
    ).scalar_one()
    pending_orders = (
        await db.execute(
            select(func.count(Order.id)).where(Order.status == "pending")
        )
    ).scalar_one()

    # 发货单统计
    total_shipments = (await db.execute(select(func.count(Shipment.id)))).scalar_one()
    shipped_shipments = (
        await db.execute(select(func.count(Shipment.id)).where(Shipment.status == "shipped"))
    ).scalar_one()

    # 平均发货时长（订单创建 → 全部发货完成，仅统计已发货订单）
    avg_hours_q = (
        select(
            func.avg(
                func.julianday(func.substr(Order.shipped_at, 1, 19))
                - func.julianday(Order.created_at)
            ) * 24.0
        )
        .where(Order.status == "shipped", Order.shipped_at.is_not(None))
    )
    avg_hours = (await db.execute(avg_hours_q)).scalar_one()

    # 预警处理情况
    alert_total = (
        await db.execute(select(func.count(Product.id)).where(Product.alert_status.is_(True)))
    ).scalar_one()

    return {
        "total_orders": total_orders,
        "shipped_orders": shipped_orders,
        "pending_orders": pending_orders,
        "ship_rate": round(shipped_orders / total_orders * 100, 1) if total_orders else 0.0,
        "total_shipments": total_shipments,
        "shipped_shipments": shipped_shipments,
        # SQLite julianday 差 × 24 = 小时数；无已发货订单时为 None
        "avg_ship_hours": round(float(avg_hours), 1) if avg_hours is not None else None,
        "alert_products": alert_total,
    }


async def finance_reconciliation(db: AsyncSession, days: int = 30) -> dict:
    """财务对账：采购应付 vs 销售应收（按供应商/平台分组）。"""
    since = datetime.now() - timedelta(days=days)

    # 采购应付（按供应商分组）
    ap_rows = (
        await db.execute(
            select(
                Supplier.name,
                func.coalesce(
                    func.sum(PurchaseOrderItem.quantity * PurchaseOrderItem.unit_price), 0.0
                ),
            )
            .select_from(PurchaseOrder)
            .join(PurchaseOrderItem, PurchaseOrderItem.purchase_order_id == PurchaseOrder.id)
            .join(Supplier, PurchaseOrder.supplier_id == Supplier.id)
            .where(PurchaseOrder.status.in_(_AP_STATUSES), PurchaseOrder.created_at >= since)
            .group_by(Supplier.name)
        )
    ).all()
    payable = [{"name": r[0], "amount": round(float(r[1]), 2)} for r in ap_rows]

    # 销售应收（按平台分组）
    ar_rows = (
        await db.execute(
            select(
                func.coalesce(Order.platform, "unknown"),
                func.coalesce(func.sum(Order.amount), 0.0),
            )
            .where(Order.status.in_(_AR_STATUSES), Order.created_at >= since)
            .group_by(func.coalesce(Order.platform, "unknown"))
        )
    ).all()
    receivable = [{"name": r[0], "amount": round(float(r[1]), 2)} for r in ar_rows]

    total_ap = round(sum(x["amount"] for x in payable), 2)
    total_ar = round(sum(x["amount"] for x in receivable), 2)
    return {
        "days": days,
        "payable": payable,
        "receivable": receivable,
        "total_payable": total_ap,
        "total_receivable": total_ar,
        "net_cash_gap": round(total_ar - total_ap, 2),  # 应收−应付（正=现金流入）
    }
