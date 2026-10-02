"""AI 路由：建议列表 / AI 建议(advice) / AI 对话(chat, SSE 流式)。

Day3 核心：advice 走 LangChain 风格 Chain（RAG + DeepSeek + 兜底）；
chat 走 SSE 流式输出（前端 fetch + ReadableStream 渲染）。
"""

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import chains, llm, prompts, rag
from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import AiSuggestion, User
from app.schemas.ai import AdviceRequest, ChatRequest
from app.services import product_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/suggestions")
async def list_suggestions(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    product_id: Optional[str] = Query(default=None, description="按商品过滤"),
    status: Optional[str] = Query(default=None, description="pending/accepted/dismissed"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """AI 建议分页列表，前端按 type 渲染建议卡片。"""
    query = select(AiSuggestion).order_by(AiSuggestion.created_at.desc())
    count_query = select(func.count(AiSuggestion.id))
    if product_id:
        query, count_query = query.where(AiSuggestion.product_id == product_id), (
            count_query.where(AiSuggestion.product_id == product_id)
        )
    if status:
        query, count_query = query.where(AiSuggestion.status == status), count_query.where(
            AiSuggestion.status == status
        )

    total = (await db.execute(count_query)).scalar_one()
    items = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
        .all()
    )
    return ok(
        {
            "items": [
                {
                    "id": s.id,
                    "type": s.type,
                    "product_id": s.product_id,
                    "content": s.content,
                    "rule_refs": s.rule_refs,
                    "status": s.status,
                    "created_at": s.created_at.isoformat(),
                }
                for s in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/advice")
async def advice(
    payload: AdviceRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """AI 结构化建议（补货/定价）：Chain 产出 → 落库 → 返回。

    无论 AI 是否可用都返回 200（source=ai 或 rule 标识来源），
    保证演示永不中断（需求 FR-2.3 兜底要求）。
    """
    product = await product_service.get_product_or_404(db, payload.product_id)

    if payload.type == "restock":
        outcome = await chains.restock_chain(db, product)
    else:
        outcome = await chains.pricing_chain(db, product)

    suggestion = AiSuggestion(
        type=payload.type,
        product_id=product.id,
        content=outcome["content"],
        rule_refs=outcome["rule_refs"],
        status="pending",
    )
    db.add(suggestion)
    await db.flush()
    await db.refresh(suggestion)

    return ok(
        {
            "suggestion_id": suggestion.id,
            "product_id": product.id,
            "type": payload.type,
            "content": outcome["content"],
            "rule_refs": outcome["rule_refs"],
            "source": outcome["source"],
        }
    )


def _sse_event(data: str) -> str:
    """封装为 SSE 事件帧；JSON 编码保证换行不破坏事件边界。"""
    return f"data: {json.dumps({'delta': data}, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """AI 对话（SSE 流式）：text/event-stream，帧格式 data: {"delta": "..."}。

    流程：RAG 检索规则拼入 system prompt → DeepSeek stream（含多轮上下文）
    → 逐帧推送 → 结束帧 data: [DONE]。LLM 不可用时推送规则引擎兜底回答。
    历史由前端回传（无状态），此处只保留最近 6 轮防 token 滥用。
    """
    rules = await rag.retrieve_rules(db, payload.message)
    system = prompts.build_chat_system(rules)
    # 截取最近 6 轮并转为 OpenAI messages 格式（防 prompt 超长/注入堆积）
    history = [
        {"role": t.role, "content": t.content} for t in payload.history[-6:]
    ]

    async def event_generator():
        try:
            async for delta in llm.stream_chat(system, payload.message, history):
                yield _sse_event(delta)
        except llm.LLMUnavailable:
            # 兜底：无密钥/未启用时，用检索到的规则原文回答，保证可用性
            rules_text = "\n".join(f"· [{r['title']}] {r['content']}" for r in rules)
            yield _sse_event(
                "【规则引擎兜底】AI 服务未启用，以下是与您问题相关的运营规则：\n"
                f"{rules_text}"
            )
        except Exception as exc:  # 网络/超时等运行时异常：如实告知但不中断连接
            yield _sse_event(f"[AI 调用异常：{type(exc).__name__}]")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
