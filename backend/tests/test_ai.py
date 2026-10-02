"""AI 模块测试：Chain 产出/兜底、RAG 检索、SSE 流式对话。

不依赖真实 DeepSeek API：autouse fixture 强制禁用真实 LLM（即使本机配置了
DEEPSEEK_API_KEY，测试也不打外部接口）；需要模拟"AI 正常/不合法输出"的用例
通过 monkeypatch 替换 llm.chat_json / stream_chat 实现。
"""

import json

import pytest

from app.ai import llm
from app.core.config import get_settings
from app.models import Product  # noqa: F401 确保 ORM 注册


@pytest.fixture(autouse=True)
def disable_real_llm(monkeypatch):
    """禁用真实 LLM，保证测试确定性（不依赖网络与外部服务配额）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "deepseek_api_key", "")


@pytest.fixture
def product_id(client, admin_headers, operator_headers):
    """前置：店铺 + 一个预警商品（stock=5, safety=10）。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "AI测试店"}, headers=admin_headers
    ).json()["data"]
    resp = client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": "AI-001", "name": "蓝牙耳机", "stock": 5, "safety_stock": 10},
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


# ---------- 补货建议 ----------

def test_advice_restock_ai_success(client, viewer_headers, product_id, monkeypatch):
    """AI 输出合法 JSON → source=ai，建议落库。"""
    async def fake_chat_json(system, user):
        return {"quantity": 42, "priority": "high", "reason": "AI：库存告急，建议补 42 件"}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    resp = client.post(
        "/api/ai/advice",
        json={"product_id": product_id, "type": "restock"},
        headers=viewer_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["source"] == "ai"
    assert data["content"]["quantity"] == 42
    assert data["rule_refs"]  # 引用了检索到的规则

    # 建议已落库且可在列表查询到
    resp = client.get(
        f"/api/ai/suggestions?product_id={product_id}&status=pending", headers=viewer_headers
    )
    assert resp.json()["data"]["total"] == 1


def test_advice_restock_fallback_when_llm_down(client, viewer_headers, product_id, monkeypatch):
    """LLM 不可用（返回 None）→ 规则引擎兜底，接口不报错（四级降级链第 3 级）。"""
    async def down(system, user):
        return None

    monkeypatch.setattr(llm, "chat_json", down)
    resp = client.post(
        "/api/ai/advice",
        json={"product_id": product_id, "type": "restock"},
        headers=viewer_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "rule"
    # 公式：max(0, 0*1.2 + 10 - 5) = 5
    assert data["content"]["quantity"] == 5
    assert "builtin-restock-formula" in data["rule_refs"]


def test_advice_restock_invalid_output_fallback(client, viewer_headers, product_id, monkeypatch):
    """AI 输出不合法（缺字段/类型错误）→ 校验失败走兜底（第 2 级）。"""
    async def bad_json(system, user):
        return {"qty": "很多", "priority": "超高"}  # 字段名错误、类型错误

    monkeypatch.setattr(llm, "chat_json", bad_json)
    resp = client.post(
        "/api/ai/advice",
        json={"product_id": product_id, "type": "restock"},
        headers=viewer_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["source"] == "rule"


# ---------- 定价建议 ----------

def test_advice_pricing_fallback(client, viewer_headers, product_id, monkeypatch):
    """定价建议兜底路径：建议价 > 成本价，范围合理。"""
    async def down(system, user):
        return None

    monkeypatch.setattr(llm, "chat_json", down)
    resp = client.post(
        "/api/ai/advice",
        json={"product_id": product_id, "type": "pricing"},
        headers=viewer_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "rule"
    content = data["content"]
    assert content["suggested_price"] > 10.0  # 高于成本价
    assert content["price_range"][0] <= content["suggested_price"] <= content["price_range"][1]
    assert len(content["competitor_prices"]) == 3


def test_pricing_competitor_prices_deterministic(client, admin_headers, operator_headers):
    """Mock 竞品价由 SKU 哈希决定：同 SKU 结果一致（可复现）。"""
    from app.ai.chains import competitor_prices
    from app.models import Product

    p = Product(sku="DET-001", name="x", cost_price=10, sale_price=100)
    assert competitor_prices(p) == competitor_prices(p)


# ---------- RAG 检索 ----------

def test_rag_keyword_scoring(client, viewer_headers):
    """RAG 关键词打分：查询与规则文本的重合度计算正确。"""
    from app.ai.rag import _keywords

    kw_q = _keywords("补货公式 安全库存")
    kw_d = _keywords("补货公式：建议补货量 = max(0, 近7天出库量)")
    # "补货"、"公式" 等双字词应命中
    assert len(kw_q & kw_d) >= 2


def test_chat_fallback_mentions_builtin_rules(client, viewer_headers):
    """规则库为空时对话兜底 → 引用内置规则（rag.BUILTIN_RULES 兜底路径）。"""
    with client.stream(
        "POST", "/api/ai/chat", json={"message": "怎么定价"}, headers=viewer_headers
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")
    # 内置定价规则出现在兜底回答里
    assert "定价策略" in body


# ---------- SSE 对话 ----------

def test_chat_sse_fallback_without_key(client, viewer_headers):
    """未配置 API Key → SSE 推送规则引擎兜底回答 + [DONE] 结束帧。"""
    with client.stream(
        "POST", "/api/ai/chat", json={"message": "这个商品该怎么补货？"}, headers=viewer_headers
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes()).decode("utf-8")

    assert "[DONE]" in body
    assert "规则引擎兜底" in body
    # 每一帧都是 data: {"delta": ...} 的 JSON，无裸换行破坏帧边界
    frames = [line for line in body.split("\n\n") if line.startswith("data: ")]
    for frame in frames[:-1]:  # 最后一帧是 [DONE]
        payload = frame.removeprefix("data: ")
        assert "delta" in json.loads(payload)


def test_chat_sse_streamed_chunks(client, viewer_headers, monkeypatch):
    """mock LLM 流式输出 → 多帧推送 + 结束帧。"""
    async def fake_stream(system, user, history=None):
        for chunk in ["建议", "补货", "42", "件"]:
            yield chunk

    monkeypatch.setattr(llm, "stream_chat", fake_stream)
    with client.stream(
        "POST", "/api/ai/chat", json={"message": "补货"}, headers=viewer_headers
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")

    assert body.count("data: ") == 5  # 4 个内容帧 + 1 个 [DONE]
    assert "[DONE]" in body
    assert "建议" in body and "42" in body


def test_chat_passes_history_to_llm(client, viewer_headers, monkeypatch):
    """多轮上下文：history 现由后端从会话表加载（方案 B），
    客户端回传的 history 字段已废弃，仅验证接口兼容不报错。"""
    with client.stream(
        "POST",
        "/api/ai/chat",
        json={"message": "继续", "history": [{"role": "user", "content": "问题1"}]},
        headers=viewer_headers,
    ) as resp:
        assert resp.status_code == 200
        b"".join(resp.iter_bytes())
    # 兜底回答正常推送，接口未因废弃字段报错
    assert resp.headers.get("x-conversation-id")
