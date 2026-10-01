"""店铺模块测试：CRUD / 凭证不回显 / 同步触发幂等 / 连通性测试。"""

import pytest

from app.utils import platform_client

MOCK_ITEMS = [
    {
        "sku": "MOCK-001",
        "name": "无线蓝牙耳机",
        "stock": 5,
        "cost_price": 35.0,
        "sale_price": 89.0,
    }
]


@pytest.fixture
def shop_id(client, admin_headers):
    """创建一个 Mock 店铺并返回 ID。"""
    resp = client.post(
        "/api/shops",
        json={"platform": "mock", "name": "测试店铺", "credentials": "abc123"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def test_shop_response_never_leaks_credentials(client, admin_headers, shop_id):
    """凭证安全：列表/详情输出任何字段都不含明文或密文凭证。"""
    resp = client.get("/api/shops", headers=admin_headers)
    assert resp.status_code == 200
    text = str(resp.json())
    assert "abc123" not in text  # 明文不回显


def test_duplicate_shop_name_conflict(client, admin_headers, shop_id):
    """同平台店铺名唯一 → 409。"""
    resp = client.post(
        "/api/shops",
        json={"platform": "mock", "name": "测试店铺"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_sync_idempotent(client, admin_headers, operator_headers, shop_id, monkeypatch):
    """同步幂等性（系统设计 §10 关键验收）：
    连续同步两次，商品数不变；库存未变化时不写流水。"""
    monkeypatch.setattr(platform_client, "fetch_products", lambda platform: MOCK_ITEMS)

    # 第一次同步：创建 1 个商品
    resp = client.post(f"/api/shops/{shop_id}/sync", headers=operator_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["task_id"]

    resp = client.get(f"/api/products?shop_id={shop_id}", headers=admin_headers)
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["stock"] == 5
    assert items[0]["alert_status"] is True  # 5 < 10 触发预警

    # 第二次同步（库存未变）：不重复建商品、不写流水
    client.post(f"/api/shops/{shop_id}/sync", headers=operator_headers)
    resp = client.get(f"/api/products?shop_id={shop_id}", headers=admin_headers)
    assert len(resp.json()["data"]["items"]) == 1

    pid = items[0]["id"]
    resp = client.get(f"/api/inventory/logs?product_id={pid}", headers=admin_headers)
    assert resp.json()["data"]["total"] == 0  # 库存没变 → 无流水


def test_sync_writes_log_on_stock_change(
    client, admin_headers, operator_headers, shop_id, monkeypatch
):
    """平台库存变化后同步：写一条盘点流水（余额与流水一致）。"""
    monkeypatch.setattr(platform_client, "fetch_products", lambda platform: MOCK_ITEMS)
    client.post(f"/api/shops/{shop_id}/sync", headers=operator_headers)

    pid = client.get(f"/api/products?shop_id={shop_id}", headers=admin_headers).json()[
        "data"
    ]["items"][0]["id"]

    # 平台侧库存变化：5 → 9，再同步
    changed = [dict(MOCK_ITEMS[0], stock=9)]
    monkeypatch.setattr(platform_client, "fetch_products", lambda platform: changed)
    client.post(f"/api/shops/{shop_id}/sync", headers=operator_headers)

    resp = client.get(f"/api/products/{pid}", headers=admin_headers)
    assert resp.json()["data"]["stock"] == 9

    resp = client.get(f"/api/inventory/logs?product_id={pid}", headers=admin_headers)
    logs = resp.json()["data"]["items"]
    assert len(logs) == 1
    assert logs[0]["type"] == "check"
    assert logs[0]["stock_before"] == 5 and logs[0]["stock_after"] == 9
    assert logs[0]["reason"] == "平台同步"


def test_connection_status(client, admin_headers, shop_id, monkeypatch):
    """连通性测试：成功 → connected；平台异常 → disconnected（不抛 500）。"""
    monkeypatch.setattr(platform_client, "fetch_products", lambda platform: list(MOCK_ITEMS))
    resp = client.post(f"/api/shops/{shop_id}/test", headers=admin_headers)
    assert resp.json()["data"]["status"] == "connected"

    def boom(platform):
        raise RuntimeError("平台不可达")

    monkeypatch.setattr(platform_client, "fetch_products", boom)
    resp = client.post(f"/api/shops/{shop_id}/test", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "disconnected"
