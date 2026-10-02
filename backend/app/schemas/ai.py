"""AI 模块 Schema：建议请求 / 对话请求。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AdviceRequest(BaseModel):
    """AI 建议请求：对指定商品请求补货或定价建议。"""

    product_id: str
    type: Literal["restock", "pricing"] = Field(description="restock=补货建议, pricing=定价建议")


class ChatTurn(BaseModel):
    """一轮历史对话（已废弃：会话历史现由后端 conversations 表持久化，
    字段保留仅为兼容旧客户端）。"""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    """AI 对话请求（SSE 流式返回）。

    conversation_id：会话 ID。为空时创建新会话（标题取消息前 30 字）；
    传入已有 ID 时追加到该会话（后端校验归属）。多轮上下文由后端
    从 conversations/chat_messages 表加载最近 6 条，前端无需回传。
    """

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    # 已废弃：保留兼容旧客户端；后端以 DB 历史为准
    history: list[ChatTurn] = Field(default_factory=list)
