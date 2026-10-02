"""会话持久化（方案 B）测试：chat 落库 / 上下文加载 / 归属隔离 / 删除。

不依赖真实 LLM（同 test_ai 的 autouse 禁用），走规则引擎兜底路径，
回复文本确定性，便于断言 assistant 消息内容。
"""

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def disable_real_llm(monkeypatch):
    """禁用真实 LLM，保证测试确定性。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "deepseek_api_key", "")


def _chat(client, headers, **payload):
    """发起 SSE 对话并消费完整个流，返回 (Response, SSE正文)。"""
    with client.stream(
        "POST", "/api/ai/chat", json=payload, headers=headers
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")
        return resp, body


def test_chat_creates_conversation_and_persists(client, viewer_headers):
    """首次对话（无 conversation_id）→ 自动建会话 + 消息落库。"""
    resp, body = _chat(client, viewer_headers, message="库存不足怎么处理？")
    assert resp.status_code == 200
    assert "[DONE]" in body

    # 会话 ID 经响应头返回（流式响应没有 JSON body 可携带）
    conv_id = resp.headers.get("x-conversation-id")
    assert conv_id

    # 会话出现在列表中，标题取首条消息前 30 字
    data = client.get("/api/ai/conversations", headers=viewer_headers).json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == conv_id
    assert data["items"][0]["title"] == "库存不足怎么处理？"

    # 消息明细：user + assistant（兜底回答）各一条
    detail = client.get(
        f"/api/ai/conversations/{conv_id}/messages", headers=viewer_headers
    ).json()["data"]
    roles = [m["role"] for m in detail["items"]]
    assert roles == ["user", "assistant"]
    assert detail["items"][0]["content"] == "库存不足怎么处理？"
    assert "规则引擎兜底" in detail["items"][1]["content"]


def test_chat_appends_to_existing_conversation(client, viewer_headers):
    """携带 conversation_id 再次对话 → 追加到同一会话（共 4 条消息）。"""
    resp1, _ = _chat(client, viewer_headers, message="第一问")
    conv_id = resp1.headers["x-conversation-id"]
    resp2, _ = _chat(client, viewer_headers, message="第二问", conversation_id=conv_id)
    assert resp2.headers["x-conversation-id"] == conv_id

    detail = client.get(
        f"/api/ai/conversations/{conv_id}/messages", headers=viewer_headers
    ).json()["data"]
    assert [m["role"] for m in detail["items"]] == ["user", "assistant"] * 2
    assert detail["items"][2]["content"] == "第二问"


def test_history_loaded_from_db_not_client(client, viewer_headers, monkeypatch):
    """多轮上下文由后端从会话表加载（客户端 history 字段已废弃）。

    捕获传给 stream_chat 的 history：第二轮应含第一轮的问与答，
    且不含当前刚发送的消息（当前消息走独立的 user 参数，防重复）。
    """
    from app.ai import llm

    captured = {}

    async def fake_stream(system, user, history=None):
        captured["user"] = user
        captured["history"] = history
        yield "好的"

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    resp1, _ = _chat(client, viewer_headers, message="第一问")
    conv_id = resp1.headers["x-conversation-id"]
    _chat(client, viewer_headers, message="第二问", conversation_id=conv_id)

    assert captured["user"] == "第二问"
    contents = [(m["role"], m["content"]) for m in captured["history"]]
    assert ("user", "第一问") in contents
    assert ("assistant", "好的") in contents
    # 当前消息不应重复出现在历史中
    assert ("user", "第二问") not in contents


def test_conversation_ownership_isolation(client, viewer_headers, admin_headers):
    """归属隔离：他人会话的消息明细/续聊/删除 → 一律 404（防探测）。"""
    resp, _ = _chat(client, viewer_headers, message="我的私有会话")
    conv_id = resp.headers["x-conversation-id"]

    # 另一个用户（admin_headers）访问 → 404
    assert client.get(
        f"/api/ai/conversations/{conv_id}/messages", headers=admin_headers
    ).status_code == 404
    resp2, _ = _chat(client, admin_headers, message="蹭一下", conversation_id=conv_id)
    assert resp2.status_code == 404
    assert client.delete(
        f"/api/ai/conversations/{conv_id}", headers=admin_headers
    ).status_code == 404

    # 本人访问不受影响
    assert client.get(
        f"/api/ai/conversations/{conv_id}/messages", headers=viewer_headers
    ).status_code == 200


def test_delete_conversation(client, viewer_headers):
    """删除会话 → 列表消失、消息明细 404，连带消息级联清理。"""
    resp, _ = _chat(client, viewer_headers, message="待删除会话")
    conv_id = resp.headers["x-conversation-id"]

    assert (
        client.delete(f"/api/ai/conversations/{conv_id}", headers=viewer_headers).status_code
        == 200
    )
    data = client.get("/api/ai/conversations", headers=viewer_headers).json()["data"]
    assert data["total"] == 0
    assert (
        client.get(
            f"/api/ai/conversations/{conv_id}/messages", headers=viewer_headers
        ).status_code
        == 404
    )


def test_title_truncated_to_30_chars(client, viewer_headers):
    """超长首条消息 → 会话标题截断到 30 字符（列宽 120 内，展示友好）。"""
    long_msg = "超" * 50
    resp, _ = _chat(client, viewer_headers, message=long_msg)
    conv_id = resp.headers["x-conversation-id"]
    data = client.get("/api/ai/conversations", headers=viewer_headers).json()["data"]
    item = next(i for i in data["items"] if i["id"] == conv_id)
    assert len(item["title"]) == 30
