"""LLM 客户端封装：DeepSeek（OpenAI 兼容协议）。

降级约定（系统设计 §4.2 四级降级链的第 1~2 级）：
- 未配置 api_key 或 ai_enabled=false → 视为"LLM 不可用"，调用方走规则引擎
- 网络/解析异常 → 重试 1 次，仍失败返回 None（同样走兜底）

跨循环安全：每次调用临时创建 AsyncOpenAI 客户端（内部 httpx.AsyncClient
绑定事件循环），避免全局客户端被 Celery 任务/请求两个循环交叉使用。
演示规模下连接开销可忽略。
"""

import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import get_settings


class LLMUnavailable(Exception):
    """LLM 不可用（未配置密钥/被禁用）。调用方应走规则引擎兜底。"""


def _new_client() -> AsyncOpenAI:
    """按当前配置创建客户端；未启用 AI 时抛 LLMUnavailable。"""
    settings = get_settings()
    if not settings.ai_enabled or not settings.deepseek_api_key:
        raise LLMUnavailable("AI 未启用或未配置 DEEPSEEK_API_KEY")
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=30.0,
        max_retries=1,
    )


def _parse_json(text: str | None) -> dict | None:
    """解析模型输出为 JSON dict；兼容 ```json 代码围栏，失败返回 None。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # 去掉 ```json ... ``` 围栏
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        result = json.loads(cleaned)
        return result if isinstance(result, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


async def chat_json(system: str, user: str) -> dict | None:
    """请求 LLM 输出 JSON（json_object 模式 + 解析失败重试 1 次）。

    返回 None 表示"本次 AI 不可用"，调用方必须兜底，不能让接口报错。
    """
    try:
        client = _new_client()
    except LLMUnavailable:
        return None

    for _ in range(2):  # 最多 2 次：第 1 次网络/解析失败后再试 1 次
        try:
            resp = await client.chat.completions.create(
                model=get_settings().deepseek_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},  # DeepSeek 支持 JSON 模式
            )
            result = _parse_json(resp.choices[0].message.content)
            if result is not None:
                return result
        except Exception:
            # 网络/超时/限流等：静默重试，最终由调用方兜底
            continue
    return None


async def stream_chat(
    system: str, user: str, history: list[dict] | None = None
) -> AsyncIterator[str]:
    """流式对话：逐段 yield 文本增量；不可用/异常时抛 LLMUnavailable 或原异常。

    history：多轮上下文（[{role, content}, ...]），按时间顺序插在 system 与
    本次提问之间；由调用方负责截断轮数（router 限制最近 6 轮）。
    """
    client = _new_client()  # 未启用时在此抛 LLMUnavailable
    messages = [{"role": "system", "content": system}, *(history or []), {"role": "user", "content": user}]
    stream = await client.chat.completions.create(
        model=get_settings().deepseek_model,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
