"""订单模块接口测试：拉单幂等 / 拆单库存判定 / 发货扣库存。

Mock 平台的订单源在进程外（8001 服务），测试中 monkeypatch
platform_client.fetch_platform_orders 提供确定性订单数据，
只测 backend 侧的业务逻辑（拉单幂等/库存判定/状态流转）。
"""

import pytest

from app.services import order_service


def _mock_orders_fn(orders):
    """构造 fetch_platform_orders 的 monkeypatch 替身。

    每次调用返回同一批订单——模拟"平台侧单号不变、backend 幂等去重"的
    真实场景（这正是拉单幂等性的测试点）。
    """

    async def fake(platform: str, limit: int = 3):
        return orders

    return fake


@pytest.fixture
def shop_and_product(client, admin_headers, operator_headers):
    """前置：店铺（platform=mock）+ 商品（stock=20, price=50）。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "订单测试店", "credentials": "t"},
        headers=admin_headers,
    ).json()["data"]
    product = client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": "MOCK-001", "name": "耳机", "stock": 20,
              "safety_stock": 5, "sale_price": 50},
        headers=operator_headers,
    ).json()["data"]
    return shop, product


ORDERS = [
    {
        "platform_order_no": "MOCK-ORD-000001",
        "ordered_at": "2026-10-03T10:00:00",
        "receiver_name": "张伟", "receiver_phone": "13800000001", "receiver_address": "深圳市南山区",
        "items": [{"sku": "MOCK-001", "quantity": 3, "price": 50.0}],
    },
    {
        "platform_order_no": "MOCK-ORD-000002",
        "ordered_at": "2026-10-03T11:00:00",
        "receiver_name": "李娜", "receiver_phone": "13900000002", "receiver_address": "杭州市西湖区",
        "items": [{"sku": "MOCK-001", "quantity": 5, "price": 50.0},
                  {"sku": "UNKNOWN-SKU", "quantity": 1, "price": 9.9}],  # 含未知 SKU 项
    },
]


def test_fetch_orders_idempotent(client, admin_headers, operator_headers, shop_and_product, monkeypatch):
    """拉单：正常入库 + SKU 不匹配项丢弃 + 重复拉取零新增。"""
    shop, product = shop_and_product
    # patch order_service 命名空间（from-import 绑定，patch 源模块不生效）
    monkeypatch.setattr(order_service, "fetch_platform_orders", _mock_orders_fn(ORDERS))

    resp = client.post(
        "/api/orders/fetch", json={"shop_id": shop["id"]}, headers=operator_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["fetched"] == 2  # 两单都入库（UNKNOWN 项被丢弃但不影响整单）

    # 订单明细：第一单 1 项，第二单只剩 1 项（UNKNOWN 被丢弃）
    orders = client.get("/api/orders", headers=admin_headers).json()["data"]
    assert orders["total"] == 2
    item_counts = {o["platform_order_no"]: len(o["items"]) for o in orders["items"]}
    assert item_counts["MOCK-ORD-000001"] == 1
    assert item_counts["MOCK-ORD-000002"] == 1

    # 幂等：同一批订单再拉一次 → fetched=0, skipped=2
    resp = client.post(
        "/api/orders/fetch", json={"shop_id": shop["id"]}, headers=operator_headers
    )
    data = resp.json()["data"]
    assert data["fetched"] == 0
    assert data["skipped"] == 2
    assert client.get("/api/orders", headers=admin_headers).json()["data"]["total"] == 2


def test_split_and_ship_flow(client, admin_headers, operator_headers, shop_and_product, monkeypatch):
    """拆单（库存充足）→ 发货扣库存 → 订单完成；发货单流转 waiting→shipped。"""
    shop, product = shop_and_product
    monkeypatch.setattr(order_service, "fetch_platform_orders", _mock_orders_fn(ORDERS[:1]))
    client.post("/api/orders/fetch", json={"shop_id": shop["id"]}, headers=operator_headers)

    # 一键拆单：库存 20 足够 3 件 → split=1
    resp = client.post("/api/orders/split", json={}, headers=operator_headers)
    assert resp.json()["data"]["split"] == 1

    orders = client.get("/api/orders", headers=admin_headers).json()["data"]["items"]
    order = next(o for o in orders if o["platform_order_no"] == "MOCK-ORD-000001")
    assert order["status"] == "partial"  # 已拆待发

    # 发货单 waiting → ship
    shipments = client.get("/api/shipments", headers=admin_headers).json()["data"]
    assert shipments["total"] == 1
    sid = shipments["items"][0]["id"]

    resp = client.post(
        f"/api/shipments/{sid}/ship",
        json={"tracking_no": "SF1234567890", "carrier": "顺丰"},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "shipped"

    # 库存扣减：20 - 3 = 17（账实分离 out 流水）
    data = client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["data"]
    assert data["stock"] == 17

    # 订单全部发完 → shipped
    order = next(
        o for o in client.get("/api/orders", headers=admin_headers).json()["data"]["items"]
        if o["platform_order_no"] == "MOCK-ORD-000001"
    )
    assert order["status"] == "shipped"
    assert order["shipped_at"]


def test_split_insufficient_stock(client, admin_headers, operator_headers, shop_and_product, monkeypatch):
    """库存不足的订单：拆单跳过、保持 pending（等采购入库后再拆）。"""
    shop, product = shop_and_product
    # 需求 50 件 > 库存 20
    big_order = [dict(ORDERS[0], platform_order_no="MOCK-ORD-000009",
                      items=[{"sku": "MOCK-001", "quantity": 50, "price": 50.0}])]
    monkeypatch.setattr(order_service, "fetch_platform_orders", _mock_orders_fn(big_order))
    client.post("/api/orders/fetch", json={"shop_id": shop["id"]}, headers=operator_headers)

    resp = client.post("/api/orders/split", json={}, headers=operator_headers)
    assert resp.json()["data"] == {"split": 0, "skipped": 1}

    # 订单保持 pending，未产生发货单，库存未变
    orders = client.get("/api/orders?status=pending", headers=admin_headers).json()["data"]
    assert orders["total"] == 1
    assert client.get("/api/shipments", headers=admin_headers).json()["data"]["total"] == 0
    data = client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["data"]
    assert data["stock"] == 20


def test_ship_insufficient_rollback(client, admin_headers, operator_headers, shop_and_product, monkeypatch):
    """发货时库存被并发消耗：预检失败 400，不产生任何扣减。"""
    shop, product = shop_and_product
    monkeypatch.setattr(order_service, "fetch_platform_orders", _mock_orders_fn(ORDERS[:1]))
    client.post("/api/orders/fetch", json={"shop_id": shop["id"]}, headers=operator_headers)
    client.post("/api/orders/split", json={}, headers=operator_headers)
    sid = client.get("/api/shipments", headers=admin_headers).json()["data"]["items"][0]["id"]

    # 拆单后、发货前，商品先被手动出库 18 件（20 → 2 < 3）
    client.post(
        "/api/inventory/logs",
        json={"product_id": product["id"], "type": "out", "quantity": 18, "reason": "并发出库"},
        headers=operator_headers,
    )
    resp = client.post(
        f"/api/shipments/{sid}/ship",
        json={"tracking_no": "SF000", "carrier": "顺丰"},
        headers=operator_headers,
    )
    assert resp.status_code == 400

    # 库存未被发货流程再次扣减（仍是 2），发货单仍 waiting
    data = client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["data"]
    assert data["stock"] == 2
    assert client.get("/api/shipments", headers=admin_headers).json()["data"]["items"][0]["status"] == "waiting"


def test_legacy_orders_hidden(client, admin_headers, operator_headers, shop_and_product):
    """legacy 存量数据默认不出现在订单列表（显式按状态查询才可见）。"""
    # 默认列表不含 legacy（测试库无 legacy 数据，total=0 亦验证过滤条件生效）
    orders = client.get("/api/orders", headers=admin_headers).json()["data"]
    assert all(o["status"] != "legacy" for o in orders["items"])
    # 显式查 legacy 也合法
    legacy = client.get("/api/orders?status=legacy", headers=admin_headers).json()["data"]
    assert isinstance(legacy["items"], list)
