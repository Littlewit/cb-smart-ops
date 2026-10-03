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

from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


class RuleUpsert(BaseModel):
    """规则知识库新增/更新请求。"""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)

from app.ai import chains, llm, prompts, rag
from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import AiSuggestion, User
from app.schemas.ai import AdviceRequest, ChatRequest
from app.services import agent_service, conversation_service, product_service, rule_service

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
            # 规则标题：前端展示用（ref 是机器主键，对运营者无可读性）
            "rule_titles": outcome.get("rule_titles", []),
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
    user: User = Depends(require_role("viewer")),
):
    """AI 对话（SSE 流式）：text/event-stream，帧格式 data: {"delta": "..."}。

    流程：会话归属校验/创建 → 用户消息落库 → RAG 检索规则拼 system prompt
    → DeepSeek stream（上下文取自 chat_messages 表最近 6 条）
    → 逐帧推送 → 完整回复落库 → 结束帧 data: [DONE]。

    会话 ID 通过响应头 X-Conversation-Id 返回（流式响应没有 JSON body 可带）。
    历史持久化（方案 B）后多轮上下文由后端加载，前端不再回传 history。
    """
    # 会话：传入则校验归属（404 防越权探测），否则以首条消息为题新建
    if payload.conversation_id:
        conv = await conversation_service.get_owned_or_404(
            db, payload.conversation_id, user.id
        )
    else:
        conv = await conversation_service.create_conversation(
            db, user.id, title=payload.message[:30]
        )
    # 多轮上下文：先取历史再落库当前消息（顺序不能反，否则当前消息在上下文里重复）
    history = await conversation_service.load_history(db, conv.id)

    rules = await rag.retrieve_rules(db, payload.message)
    system = prompts.build_chat_system(rules)

    # 用户消息立即落库：即使客户端中途断开，输入也已保留
    await conversation_service.append_message(db, conv.id, "user", payload.message)

    async def event_generator():
        """流式生成器：边推帧边累积回复，结束后整体落库。

        try/finally 保证异常路径（兜底/网络错误/客户端断开）也保留已收到的
        部分回复，便于刷新后查看当时进行到哪。
        """
        reply_parts: list[str] = []
        try:
            async for delta in llm.stream_chat(system, payload.message, history):
                reply_parts.append(delta)
                yield _sse_event(delta)
        except llm.LLMUnavailable:
            # 兜底：无密钥/未启用时，用检索到的规则原文回答，保证可用性
            rules_text = "\n".join(f"· [{r['title']}] {r['content']}" for r in rules)
            text = (
                "【规则引擎兜底】AI 服务未启用，以下是与您问题相关的运营规则：\n"
                f"{rules_text}"
            )
            reply_parts.append(text)
            yield _sse_event(text)
        except Exception as exc:  # 网络/超时等运行时异常：如实告知但不中断连接
            text = f"[AI 调用异常：{type(exc).__name__}]"
            reply_parts.append(text)
            yield _sse_event(text)
        finally:
            # 完整回复（或中断时的部分回复）落库
            await conversation_service.append_message(
                db, conv.id, "assistant", "".join(reply_parts)
            )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conv.id,
        },
    )


# ---------- 会话管理（方案 B：对话历史后端持久化） ----------


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("viewer")),
):
    """当前用户的会话列表（按更新时间倒序），前端侧栏渲染。"""
    items = await conversation_service.list_conversations(db, user.id)
    return ok({"items": items, "total": len(items)})


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("viewer")),
):
    """会话消息明细（正序），用于切换会话/刷新后恢复气泡。"""
    await conversation_service.get_owned_or_404(db, conversation_id, user.id)
    items = await conversation_service.list_messages(db, conversation_id)
    return ok({"conversation_id": conversation_id, "items": items})


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("viewer")),
):
    """删除会话（归属校验后连带消息级联清理）。"""
    await conversation_service.get_owned_or_404(db, conversation_id, user.id)
    await conversation_service.delete_conversation(db, conversation_id)
    await db.commit()
    return ok({"id": conversation_id, "deleted": True})


# ---------- Agent 工作流 + 知识库管理（ERP 扩展） ----------


class AgentPlanRequest(BaseModel):
    """Agent 补货计划请求：供应商缺省取第一个启用供应商。"""

    supplier_id: str | None = Field(default=None, description="指定供应商；缺省自动选择")


class SuggestionToPoRequest(BaseModel):
    """建议转采购单请求。"""

    supplier_id: str = Field(min_length=1)


@router.post("/agent/restock-plan")
async def agent_restock_plan(
    payload: AgentPlanRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Agent 补货计划工作流（SSE）：预警扫描 → LLM 补货量 → 生成采购单草稿。

    帧格式：data: {"step": key, "detail": ...}（工作流时间线）+
    结束前 data: {"delta": "{\"po_id\"...}"}（生成结果，前端跳转采购详情）。
    """
    return StreamingResponse(
        agent_service.run_restock_plan(db, user.id, payload.supplier_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/suggestions/{suggestion_id}/to-purchase-order")
async def suggestion_to_po(
    suggestion_id: str,
    payload: SuggestionToPoRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """单条补货建议转采购单草稿（建议卡片"转采购单"按钮）。"""
    po = await agent_service.suggestion_to_purchase_order(
        db, suggestion_id, payload.supplier_id, user.id
    )
    return ok({"id": po.id, "po_no": po.po_no, "status": po.status})


# ---------- 运营规则知识库管理（RAG 数据源） ----------


@router.get("/rules")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """规则知识库列表。"""
    items = await rule_service.list_rules(db)
    return ok(
        {
            "items": [
                {"id": r.id, "title": r.title, "content": r.content, "created_at": r.created_at.isoformat()}
                for r in items
            ],
            "total": len(items),
        }
    )


@router.post("/rules", status_code=201)
async def create_rule(
    payload: RuleUpsert,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """新增运营规则（立即生效于 RAG 检索）。"""
    rule = await rule_service.create_rule(db, payload.title, payload.content)
    return ok({"id": rule.id, "title": rule.title})


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: RuleUpsert,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """更新运营规则。"""
    rule = await rule_service.update_rule(db, rule_id, payload.title, payload.content)
    return ok({"id": rule.id, "title": rule.title})


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """删除运营规则。"""
    await rule_service.delete_rule(db, rule_id)
    return ok({"id": rule_id, "deleted": True})
