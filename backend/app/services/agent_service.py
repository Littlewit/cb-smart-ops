"""AI Agent 业务：补货计划工作流（SSE 步骤输出）+ 建议转采购单。

Agent 工作流（简历叙事核心"AI Agent 驱动的采购执行闭环"）：
    1. 扫描预警商品
    2. 逐商品调用 restock_chain 计算补货量（LLM + RAG，四级降级）
    3. 汇总补货清单（quantity=0 的跳过）
    4. 生成采购单草稿（单供应商收敛，多供应商分组为 P1）

SSE 帧格式（复用现有 SSE 基建）：
    data: {"step": "<key>", "detail": "<人类可读进度>"}   ← 工作流步骤
    data: {"delta": "<总结文本>"}                          ← 可选总结
    data: [DONE]
"""

from typing import AsyncIterator, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import chains
from app.models import AiSuggestion, Product, PurchaseOrder, Supplier
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderItemIn
from app.services import purchase_service


async def _pick_supplier(db: AsyncSession, supplier_id: Optional[str]) -> Supplier:
    """选定供应商：显式指定则校验，否则取第一个启用的供应商。"""
    if supplier_id:
        sup = await db.get(Supplier, supplier_id)
        if sup is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "供应商不存在")
        return sup
    sup = (
        await db.execute(select(Supplier).where(Supplier.status == "active").limit(1))
    ).scalar_one_or_none()
    if sup is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "请先创建供应商，Agent 才能生成采购单")
    return sup


def _sse_step(key: str, detail: str) -> str:
    """封装工作流步骤帧（JSON 编码保证换行不破坏事件边界）。"""
    import json

    return f"data: {json.dumps({'step': key, 'detail': detail}, ensure_ascii=False)}\n\n"


async def run_restock_plan(
    db: AsyncSession,
    user_id: Optional[str],
    supplier_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Agent 补货计划工作流（SSE 生成器）。

    每个步骤 yield 一帧 step；全部采购单生成后推 done 帧 + [DONE]。
    中途异常（无供应商等）转 step 帧输出错误后正常结束（连接不中断）。
    """
    import json

    # 步骤 1：扫描预警商品
    alerts = list(
        (
            await db.execute(
                select(Product)
                .where(Product.alert_status.is_(True))
                .order_by(Product.stock.asc())
                .limit(10)  # 上限保护：预警商品过多时控制 LLM 调用次数与时延
            )
        ).scalars()
    )
    if not alerts:
        yield _sse_step("done", "当前无预警商品，无需生成采购计划")
        yield "data: [DONE]\n\n"
        return

    yield _sse_step("scan", f"发现 {len(alerts)} 个预警商品：{'、'.join(p.sku for p in alerts)}")

    # 步骤 2：逐商品计算补货量（LLM + RAG，四级降级保证必出结果）
    plan: list[tuple[Product, int, str, list[str]]] = []  # (商品, 补货量, 来源, 引用规则)
    for product in alerts:
        try:
            outcome = await chains.restock_chain(db, product)
            qty = int(outcome["content"].get("quantity", 0))
            source = outcome.get("source", "rule")
        except Exception as exc:  # 单商品失败不阻断整体（Agent 容错）
            yield _sse_step("calc", f"{product.sku} 计算失败（{type(exc).__name__}），已跳过")
            continue
        if qty <= 0:
            yield _sse_step("calc", f"{product.sku} 无需补货（{source}），跳过")
            continue
        plan.append((product, qty, source, outcome.get("rule_refs", [])))
        yield _sse_step(
            "calc",
            f"{product.sku} 建议补货 {qty} 件（来源：{'DeepSeek' if source == 'ai' else '规则引擎'}）",
        )

    if not plan:
        yield _sse_step("done", "所有预警商品均无需补货，未生成采购单")
        return

    # 步骤 3：确定供应商
    try:
        supplier = await _pick_supplier(db, supplier_id)
    except HTTPException as exc:
        yield _sse_step("done", f"无法生成采购单：{exc.detail}")
        yield "data: [DONE]\n\n"
        return
    yield _sse_step("group", f"补货项已按供应商分组：{supplier.name}（{len(plan)} 项）")

    # 步骤 4：生成采购单草稿（unit_price 取商品成本价；建议留痕 created_by）
    create_payload = PurchaseOrderCreate(
        supplier_id=supplier.id,
        remark="AI Agent 补货计划自动生成",
        items=[
            PurchaseOrderItemIn(product_id=p.id, quantity=q, unit_price=p.cost_price)
            for p, q, _, _ in plan
        ],
    )
    po = await purchase_service.create_po(db, create_payload, user_id)
    total_qty = sum(q for _, q, _, _ in plan)
    yield _sse_step("po", f"已生成采购单草稿 {po.po_no}（{len(plan)} 项 / 共 {total_qty} 件）")
    yield _sse_step("done", "工作流完成：生成 1 张采购单，请到采购管理页审核提交")
    yield f"data: {json.dumps({'delta': json.dumps({'po_id': po.id, 'po_no': po.po_no}, ensure_ascii=False)}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def suggestion_to_purchase_order(
    db: AsyncSession, suggestion_id: str, supplier_id: str, user_id: Optional[str]
) -> PurchaseOrder:
    """单条 AI 补货建议 → 采购单草稿（建议卡片上的"转采购单"按钮）。

    仅支持 restock 且 quantity > 0 的建议；unit_price 取商品成本价快照。
    """
    suggestion = await db.get(AiSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "建议不存在")
    if suggestion.type != "restock":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "仅补货建议可转采购单")
    quantity = int(suggestion.content.get("quantity", 0))
    if quantity <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该建议无需补货（quantity=0），不可转采购单")
    if suggestion.product_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该建议未关联商品")

    product = await db.get(Product, suggestion.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "建议关联的商品不存在")

    create_payload = PurchaseOrderCreate(
        supplier_id=supplier_id,
        remark=f"由 AI 建议 {suggestion.id[:8]} 转生成",
        items=[PurchaseOrderItemIn(product_id=product.id, quantity=quantity, unit_price=product.cost_price)],
    )
    return await purchase_service.create_po(db, create_payload, user_id)
