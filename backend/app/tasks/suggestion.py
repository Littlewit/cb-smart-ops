"""补货建议任务（Day2：规则引擎兜底版；Day3 将计算部分替换为 DeepSeek + RAG）。

兜底公式（系统设计 §4.2）：
    建议补货量 = max(0, 近7天出库量 × 1.2 + 安全库存 − 当前库存)
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.core.database import task_session
from app.models import AiSuggestion, InventoryLog, Product
from app.tasks.celery_app import celery_app


def _calc_restock(sales7: int, stock: int, safety_stock: int) -> dict:
    """规则引擎计算补货建议（纯函数，便于测试）。

    priority 语义：high=缺货 / medium=需尽快补 / low=需补但可等 /
    none=无需行动（quantity=0 时不用 low——low 会被误读为"少量补一点"）。
    """
    quantity = max(0, int(sales7 * 1.2) + safety_stock - stock)
    if stock == 0:
        priority = "high"
    elif quantity > 0:
        priority = "medium"
    else:
        priority = "none"
    reason = (
        f"近7天出库{sales7}件，当前库存{stock}件"
        + (f"低于安全库存{safety_stock}件" if stock < safety_stock else "")
        + (
            f"，建议补货{quantity}件"
            if quantity > 0
            else f"，库存充足（{stock}件 ≥ 安全库存{safety_stock}件），无需补货"
        )
    )
    return {"quantity": quantity, "priority": priority, "reason": reason}


@celery_app.task(name="app.tasks.suggestion.generate_restock_suggestions_task")
def generate_restock_suggestions_task() -> dict:
    """为所有预警商品生成补货建议；已有 pending 建议的商品跳过（避免刷屏）。"""
    return asyncio.run(_generate())


async def _generate() -> dict:
    async with task_session() as session:
        products = (
            await session.execute(select(Product).where(Product.alert_status.is_(True)))
        ).scalars().all()

        generated = 0
        week_ago = datetime.now() - timedelta(days=7)
        for product in products:
            # 已有未处理的补货建议则跳过
            exists = await session.execute(
                select(AiSuggestion.id).where(
                    AiSuggestion.product_id == product.id,
                    AiSuggestion.type == "restock",
                    AiSuggestion.status == "pending",
                )
            )
            if exists.scalar_one_or_none() is not None:
                continue

            # 近 7 天出库量（销量代理指标；Mock 阶段无真实订单流水）
            sales7 = (
                await session.execute(
                    select(func.coalesce(func.sum(InventoryLog.quantity), 0)).where(
                        InventoryLog.product_id == product.id,
                        InventoryLog.type == "out",
                        InventoryLog.created_at >= week_ago,
                    )
                )
            ).scalar_one()

            suggestion = _calc_restock(int(sales7), product.stock, product.safety_stock)
            session.add(
                AiSuggestion(
                    type="restock",
                    product_id=product.id,
                    content=suggestion,
                    # Day3 接入 RAG 后这里填引用的规则文档 id
                    rule_refs=[],
                    status="pending",
                )
            )
            generated += 1

        await session.flush()
        return {"alert_products": len(products), "generated": generated}
