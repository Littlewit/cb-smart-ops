"""AI 模块 Schema：建议请求 / 对话请求。"""

from typing import Literal

from pydantic import BaseModel, Field


class AdviceRequest(BaseModel):
    """AI 建议请求：对指定商品请求补货或定价建议。"""

    product_id: str
    type: Literal["restock", "pricing"] = Field(description="restock=补货建议, pricing=定价建议")


class ChatRequest(BaseModel):
    """AI 对话请求（SSE 流式返回）。"""

    message: str = Field(min_length=1, max_length=2000)
