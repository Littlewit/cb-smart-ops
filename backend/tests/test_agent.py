"""AI Agent 工作流测试：补货计划 SSE / 建议转采购单 / 规则知识库 CRUD。

禁用真实 LLM（autouse），restock_chain 走规则引擎兜底——
补货量确定性可断言（预警商品 stock=5, safety=10 → max(0, 0×1.2+10−5)=5）。
"""

import json

import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def disable_real_llm(monkeypatch):
    """禁用真实 LLM：Agent 内部 restock_chain 走规则引擎兜底，结果确定。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "deepseek_api_key", "")


def _setup_alert_product(client, admin_headers, operator_headers, sku="AGT-001"):
    """前置：店铺 + 预警商品（stock=5 < safety=10）。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": f"Agent店-{sku}"}, headers=admin_headers
    ).json()["data"]
    product = client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": sku, "name": "Agent测试品", "stock": 5, "safety_stock": 10,
              "cost_price": 8.0},
        headers=operator_headers,
    ).json()["data"]
    return shop, product


def _setup_supplier(client, operator_headers, name="Agent供应商"):
    return client.post("/api/suppliers", json={"name": name}, headers=operator_headers).json()["data"]


def _consume_sse(client, path, payload, headers):
    """消费 SSE 流返回帧列表（保留 step/delta/[DONE] 原文）。"""
    with client.stream("POST", path, json=payload, headers=headers) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")
        return resp, [
            line.removeprefix("data: ")
            for line in body.split("\n\n")
            if line.startswith("data: ")
        ]


def test_agent_restock_plan_generates_po(client, admin_headers, operator_headers):
    """Agent 工作流闭环：预警扫描 → 计算 → 生成采购单草稿（含批次前置验证）。"""
    _, product = _setup_alert_product(client, admin_headers, operator_headers)
    supplier = _setup_supplier(client, operator_headers)

    resp, frames = _consume_sse(
        client, "/api/ai/agent/restock-plan", {"supplier_id": supplier["id"]}, operator_headers
    )
    assert resp.status_code == 200
    assert frames[-1] == "[DONE]"

    steps = [json.loads(f) for f in frames[:-1]]
    keys = [s.get("step") for s in steps]
    assert "scan" in keys and "calc" in keys and "po" in keys and "done" in keys

    # 规则引擎兜底补货量：max(0, 0*1.2 + 10 - 5) = 5
    calc = next(s for s in steps if s.get("step") == "calc")
    assert "5 件" in calc["detail"]

    # 采购单草稿已生成且明细正确（成本价 8.0 × 5 件）
    po_step = next(s for s in steps if s.get("step") == "po")
    assert "0001" in po_step["detail"]
    delta = json.loads(json.loads(next(f for f in frames[:-1] if '"delta"' in f))["delta"])
    detail = client.get(
        f"/api/purchase-orders/{delta['po_id']}", headers=admin_headers
    ).json()["data"]
    assert detail["status"] == "draft"
    assert detail["items"][0]["product_id"] == product["id"]
    assert detail["items"][0]["quantity"] == 5
    assert detail["items"][0]["unit_price"] == 8.0


def test_agent_no_alert_products(client, admin_headers, operator_headers):
    """无预警商品 → done 帧提示，不生成采购单。"""
    # 不建任何预警商品（本测试库为空）
    _setup_supplier(client, operator_headers)
    resp, frames = _consume_sse(
        client, "/api/ai/agent/restock-plan", {}, operator_headers
    )
    assert resp.status_code == 200
    steps = [json.loads(f) for f in frames[:-1] if f != "[DONE]"]
    assert steps[-1]["step"] == "done"
    assert "无预警商品" in steps[-1]["detail"]


def test_agent_without_supplier(client, admin_headers, operator_headers):
    """无供应商 → 工作流正常结束但提示先创建供应商（连接不中断）。"""
    _setup_alert_product(client, admin_headers, operator_headers)
    resp, frames = _consume_sse(client, "/api/ai/agent/restock-plan", {}, operator_headers)
    steps = [json.loads(f) for f in frames[:-1] if f != "[DONE]"]
    assert frames[-1] == "[DONE]"
    assert "请先创建供应商" in steps[-1]["detail"]


def test_suggestion_to_purchase_order(client, admin_headers, operator_headers):
    """单条建议转采购单：quantity 快照 + 成本价 + 非补货建议 400。"""
    _, product = _setup_alert_product(client, admin_headers, operator_headers)
    supplier = _setup_supplier(client, operator_headers)

    # 先用 Agent 生成建议（advice 接口，规则引擎兜底 quantity=5）
    advice = client.post(
        "/api/ai/advice", json={"product_id": product["id"], "type": "restock"},
        headers=operator_headers,
    ).json()["data"]
    suggestion_id = advice["suggestion_id"]

    # 转采购单
    resp = client.post(
        f"/api/ai/suggestions/{suggestion_id}/to-purchase-order",
        json={"supplier_id": supplier["id"]},
        headers=operator_headers,
    )
    assert resp.status_code == 200, resp.text
    po = resp.json()["data"]
    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=admin_headers).json()["data"]
    assert detail["items"][0]["quantity"] == 5
    assert detail["items"][0]["unit_price"] == 8.0
    assert "AI 建议" in detail["remark"]

    # 定价建议不可转采购单（400）
    pricing = client.post(
        "/api/ai/advice", json={"product_id": product["id"], "type": "pricing"},
        headers=operator_headers,
    ).json()["data"]
    resp = client.post(
        f"/api/ai/suggestions/{pricing['suggestion_id']}/to-purchase-order",
        json={"supplier_id": supplier["id"]},
        headers=operator_headers,
    )
    assert resp.status_code == 400


def test_rule_knowledge_base_crud(client, admin_headers, operator_headers):
    """规则知识库 CRUD：新增/重名 409/更新/删除/RBAC。"""
    # 新增（规则属于 AI 前缀：/api/ai/rules）
    resp = client.post(
        "/api/ai/rules",
        json={"title": "临期品处理", "content": "效期剩余 30 天内打折清仓"},
        headers=operator_headers,
    )
    assert resp.status_code == 201
    rid = resp.json()["data"]["id"]

    # 重名 409
    assert (
        client.post(
            "/api/ai/rules", json={"title": "临期品处理", "content": "x"}, headers=operator_headers
        ).status_code
        == 409
    )

    # 更新
    resp = client.put(
        f"/api/ai/rules/{rid}", json={"title": "临期品处理", "content": "效期 30 天内五折"},
        headers=operator_headers,
    )
    assert resp.status_code == 200

    # 列表与详情
    data = client.get("/api/ai/rules", headers=admin_headers).json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["content"] == "效期 30 天内五折"

    # 删除后列表为空
    assert client.delete(f"/api/ai/rules/{rid}", headers=operator_headers).status_code == 200
    assert client.get("/api/ai/rules", headers=admin_headers).json()["data"]["total"] == 0

    # RBAC：未登录不可写
    assert client.post("/api/ai/rules", json={"title": "x", "content": "y"}).status_code == 401
