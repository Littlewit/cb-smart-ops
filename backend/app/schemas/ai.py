"""AI 模块 Schema：建议请求 / 对话请求。"""

from typing import Literal

from pydantic import BaseModel, Field


class AdviceRequest(BaseModel):
    """AI 建议请求：对指定商品请求补货或定价建议。"""

    product_id: str
    type: Literal["restock", "pricing"] = Field(description="restock=补货建议, pricing=定价建议")


class ChatTurn(BaseModel):
    """一轮历史对话（多轮上下文由前端回传，后端无状态不存会话）。"""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    """AI 对话请求（SSE 流式返回）。

    history：最近几轮对话，由前端从界面消息列表截取回传；
    后端不落库（演示级约束），因此接口保持无状态、可水平扩展。
    """

    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list)
