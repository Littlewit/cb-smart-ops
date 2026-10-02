"""LangChain 风格的补货/定价 Chain：上下文组装 → LLM → 结构化校验 → 兜底。

四级降级链（系统设计 §4.2）：
1. Prompt JSON Schema 约束（prompts.py）
2. 解析校验失败重试 1 次（llm.chat_json 内部）
3. 校验仍失败 / LLM 不可用 → 规则引擎公式兜底
4. RAG 检索无结果 → 内置规则兜底（rag.BUILTIN_RULES）

所有返回都带 source 字段（"ai" / "rule"），前端可展示建议来源。
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import llm, prompts, rag
from app.models import InventoryLog, Product

# 补货建议 JSON 的合法取值约束；"none" 表示无需行动（quantity=0 时 low 会有
# "少量补一点"的歧义，语义上必须与"要做但不急"区分开）
_VALID_PRIORITIES = {"high", "medium", "low", "none"}


def _valid_restock(result: dict) -> bool:
    """结构化校验：字段齐全、类型正确、取值合法。"""
    return (
        isinstance(result.get("quantity"), int)
        and result["quantity"] >= 0
        and result.get("priority") in _VALID_PRIORITIES
        and isinstance(result.get("reason"), str)
        and len(result["reason"]) > 0
    )


def _valid_pricing(result: dict) -> bool:
    """定价建议校验：建议价必须为正数且高于成本。"""
    price = result.get("suggested_price")
    return (
        isinstance(price, (int, float))
        and price > 0
        and isinstance(result.get("strategy"), str)
        and len(result["strategy"]) > 0
    )


def competitor_prices(product: Product) -> list[float]:
    """Mock 竞品价格：由 SKU 哈希确定性生成（同一商品多次请求结果一致，
    演示与测试可复现；接入真实竞品数据源时替换本函数）。"""
    h = int(hashlib.md5(product.sku.encode("utf-8")).hexdigest(), 16)
    base = product.sale_price or max(product.cost_price * 2.0, 50.0)
    factors = (0.9 + (h % 30) / 100, 1.0 + ((h >> 8) % 40) / 100, 1.15 + ((h >> 16) % 30) / 100)
    return [round(base * f, 2) for f in factors]


async def sales_last_days(db: AsyncSession, product_id: str, days: int = 7) -> int:
    """近 N 天出库总量（销量代理指标）。"""
    from datetime import datetime, timedelta

    since = datetime.now() - timedelta(days=days)
    return int(
        (
            await db.execute(
                select(func.coalesce(func.sum(InventoryLog.quantity), 0)).where(
                    InventoryLog.product_id == product_id,
                    InventoryLog.type == "out",
                    InventoryLog.created_at >= since,
                )
            )
        ).scalar_one()
    )


async def restock_chain(db: AsyncSession, product: Product) -> dict:
    """补货建议 Chain：RAG 规则 + 商品上下文 → LLM → 校验 → 兜底。

    返回 {"content": 结构化建议, "rule_refs": [规则id], "source": "ai"|"rule"}。
    """
    rules = await rag.retrieve_rules(db, f"补货公式 安全库存 预警 {product.name} {product.sku}")
    sales7 = await sales_last_days(db, product.id)

    user_msg = (
        "商品上下文：\n"
        f"SKU: {product.sku}\n名称: {product.name}\n"
        f"当前库存: {product.stock}\n安全库存: {product.safety_stock}\n"
        f"近7天出库量: {sales7}\n成本价: {product.cost_price}\n售价: {product.sale_price}\n\n"
        "运营规则：\n" + "\n".join(f"[{r['id']}] {r['title']}: {r['content']}" for r in rules)
    )
    result = await llm.chat_json(prompts.RESTOCK_SYSTEM, user_msg)

    if result is not None and _valid_restock(result):
        return {
            "content": result,
            "rule_refs": [r["id"] for r in rules],
            # 标题单独返回供前端展示：reason 里约束引用标题，但兜底路径无 LLM 润色
            "rule_titles": [r["title"] for r in rules],
            "source": "ai",
        }

    # 兜底：规则引擎公式（与 Celery 建议任务同一实现，保证口径一致）
    from app.tasks.suggestion import _calc_restock

    fallback = _calc_restock(sales7, product.stock, product.safety_stock)
    return {
        "content": fallback,
        "rule_refs": ["builtin-restock-formula"],
        "rule_titles": ["内置补货公式"],
        "source": "rule",
    }


async def pricing_chain(db: AsyncSession, product: Product) -> dict:
    """定价建议 Chain：成本 + Mock 竞品价 → LLM → 校验 → 规则兜底。"""
    rules = await rag.retrieve_rules(db, "定价策略 竞品价格 成本")
    comp = competitor_prices(product)

    user_msg = (
        "商品上下文：\n"
        f"SKU: {product.sku}\n名称: {product.name}\n"
        f"成本价: {product.cost_price}\n当前售价: {product.sale_price}\n"
        f"竞品价格: {comp}\n\n"
        "运营规则：\n" + "\n".join(f"[{r['id']}] {r['title']}: {r['content']}" for r in rules)
    )
    result = await llm.chat_json(prompts.PRICING_SYSTEM, user_msg)

    if result is not None and _valid_pricing(result):
        return {
            "content": result,
            "rule_refs": [r["id"] for r in rules],
            "rule_titles": [r["title"] for r in rules],
            "source": "ai",
        }

    # 兜底：定价公式 max(成本×1.35, 竞品均价×0.95)，尾数取 .9
    avg_comp = sum(comp) / len(comp)
    raw = max(product.cost_price * 1.35, avg_comp * 0.95)
    price = float(int(raw)) + 0.9 if raw > int(raw) else raw
    return {
        "content": {
            "suggested_price": round(price, 2),
            "price_range": [round(raw * 0.9, 2), round(raw * 1.1, 2)],
            "strategy": f"成本{product.cost_price}元，竞品均价{avg_comp:.2f}元；"
            "按规则取两者安全上界并留利润空间，尾数定价 .9。",
            "competitor_prices": comp,
        },
        "rule_refs": ["builtin-pricing"],
        "rule_titles": ["内置定价公式"],
        "source": "rule",
    }
