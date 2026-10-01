"""Celery 任务测试（eager 模式同步执行）。

覆盖两个关键验收点：
1. 同步任务幂等 + 差异写流水
2. 补货建议任务：规则引擎公式正确 + pending 去重
"""

import pytest

from app.tasks.suggestion import generate_restock_suggestions_task
from app.tasks.sync import sync_shop_task
from app.utils import platform_client


@pytest.fixture
def shop_and_product(client, admin_headers, operator_headers):
    """前置：店铺 + 一个预警商品（stock=0, safety=5），返回 (shop_id, product_id)。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "任务测试店"}, headers=admin_headers
    ).json()["data"]
    resp = client.post(
        "/api/products",
        json={
            "shop_id": shop["id"],
            "sku": "T-001",
            "name": "任务测试商品",
            "stock": 0,
            "safety_stock": 5,
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    return shop["id"], resp.json()["data"]["id"]


def test_sync_task_direct_call(client, admin_headers, operator_headers, shop_and_product, monkeypatch):
    """直接调用同步任务：更新已有商品 + 新建商品，结果计数正确。"""
    shop_id, product_id = shop_and_product
    items = [
        # 已存在的 T-001：库存 0 → 7（应触发一次盘点流水）
        {"sku": "T-001", "name": "任务测试商品", "stock": 7, "sale_price": 9.9},
        # 新商品：任务同步新建
        {"sku": "T-002", "name": "新同步商品", "stock": 50, "sale_price": 19.9},
    ]
    monkeypatch.setattr(platform_client, "fetch_products", lambda platform: items)

    result = sync_shop_task(shop_id)  # eager 模式下可直接调用
    assert result["created"] == 1
    assert result["updated"] == 1

    # 验证数据库结果（走 API 查询，与任务同库）
    data = client.get(f"/api/products/{product_id}", headers=admin_headers).json()["data"]
    assert data["stock"] == 7
    assert data["alert_status"] is False  # 7 >= 5 解除预警

    resp = client.get(f"/api/inventory/logs?product_id={product_id}", headers=admin_headers)
    logs = resp.json()["data"]["items"]
    assert len(logs) == 1 and logs[0]["stock_after"] == 7


def test_restock_suggestion_formula(client, admin_headers, operator_headers, shop_and_product):
    """补货建议公式：sales7=0 时 quantity = max(0, 0 + safety - stock) = 5。"""
    shop_id, product_id = shop_and_product

    result = generate_restock_suggestions_task()
    assert result["generated"] == 1

    resp = client.get(
        f"/api/ai/suggestions?product_id={product_id}&status=pending",
        headers=admin_headers,
    )
    suggestions = resp.json()["data"]["items"]
    assert len(suggestions) == 1
    content = suggestions[0]["content"]
    assert content["quantity"] == 5  # 0*1.2 + 5 - 0
    assert content["priority"] == "high"  # stock=0 优先级最高
    assert suggestions[0]["type"] == "restock"

    # 再次执行：pending 建议已存在 → 去重不重复生成
    result = generate_restock_suggestions_task()
    assert result["generated"] == 0
