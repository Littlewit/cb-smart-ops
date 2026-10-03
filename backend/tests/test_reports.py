"""报表接口测试：CEO 看板 / 运营绩效 / 财务对账。

造数据路径：店铺+商品 → 采购单+收货（产生应付+库存）→ 拉单+拆单+发货
（产生应收+出库流水）→ 断言聚合口径。
"""

import pytest

from app.services import order_service


@pytest.fixture
def shop_and_product(client, admin_headers, operator_headers):
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "报表测试店", "credentials": "t"},
        headers=admin_headers,
    ).json()["data"]
    product = client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": "RP-001", "name": "报表商品", "stock": 10,
              "safety_stock": 5, "cost_price": 20.0, "sale_price": 50.0},
        headers=operator_headers,
    ).json()["data"]
    return shop, product


def _seed_remote_order(sku="RP-001", qty=4):
    """一条 Mock 平台订单（发货后 GMV=200, 毛利=(50-20)*4=120）。"""
    return {
        "platform_order_no": "MOCK-RP-000001",
        "ordered_at": "2026-10-03T10:00:00",
        "receiver_name": "测试收货人", "receiver_phone": "138", "receiver_address": "深圳",
        "items": [{"sku": sku, "quantity": qty, "price": 50.0}],
    }


def test_ceo_and_finance_flow(client, admin_headers, operator_headers, shop_and_product, monkeypatch):
    """全链路造数后验证 CEO 看板与财务对账的聚合口径。"""
    shop, product = shop_and_product
    sup = client.post("/api/suppliers", json={"name": "报表供应商"}, headers=operator_headers).json()["data"]

    # 1) 采购 6 件 × 20 = 120 应付，收货入库（库存 10+6=16）
    po = client.post(
        "/api/purchase-orders",
        json={"supplier_id": sup["id"], "items": [{"product_id": product["id"], "quantity": 6, "unit_price": 20.0}]},
        headers=operator_headers,
    ).json()["data"]
    client.post(f"/api/purchase-orders/{po['id']}/submit", headers=operator_headers)
    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=operator_headers).json()["data"]
    client.post(
        f"/api/purchase-orders/{po['id']}/receive",
        json={"items": [{"item_id": detail["items"][0]["id"], "quantity": 6}]},
        headers=operator_headers,
    )

    # 2) 拉单（4 件 × 50 = 200 应收）→ 拆单 → 发货（库存 16-4=12）
    async def fake_fetch(platform: str, limit: int = 3):
        return [_seed_remote_order()]

    monkeypatch.setattr(order_service, "fetch_platform_orders", fake_fetch)
    client.post("/api/orders/fetch", json={"shop_id": shop["id"]}, headers=operator_headers)
    client.post("/api/orders/split", json={}, headers=operator_headers)
    sid = client.get("/api/shipments", headers=admin_headers).json()["data"]["items"][0]["id"]
    client.post(
        f"/api/shipments/{sid}/ship", json={"tracking_no": "SF-REPORT", "carrier": "顺丰"},
        headers=operator_headers,
    )

    # 3) CEO 看板口径
    ceo = client.get("/api/reports/ceo?days=30", headers=admin_headers).json()["data"]
    assert ceo["gmv"] == 200.0
    assert ceo["gross_profit"] == 120.0  # (50-20)*4
    assert ceo["gross_margin"] == 60.0
    assert ceo["total_stock"] == 12
    assert ceo["alert_count"] == 0
    assert len(ceo["sales_trend"]) == 30  # 空缺日补 0，折线连续

    # 4) 财务对账口径
    fin = client.get("/api/reports/finance?days=30", headers=admin_headers).json()["data"]
    assert fin["total_payable"] == 120.0
    assert fin["total_receivable"] == 200.0
    assert fin["net_cash_gap"] == 80.0
    assert fin["payable"][0]["name"] == "报表供应商"
    assert fin["receivable"][0]["name"] == "mock"

    # 5) 运营绩效口径
    perf = client.get("/api/reports/performance", headers=admin_headers).json()["data"]
    assert perf["total_orders"] == 1
    assert perf["shipped_orders"] == 1
    assert perf["ship_rate"] == 100.0
    assert perf["shipped_shipments"] == 1
    assert perf["avg_ship_hours"] is not None  # 已发货订单有时效


def test_reports_empty_data(client, admin_headers):
    """空库：聚合接口不报错，全部零值（折线空趋势不异常）。"""
    ceo = client.get("/api/reports/ceo", headers=admin_headers).json()["data"]
    assert ceo["gmv"] == 0.0
    assert ceo["gross_margin"] == 0.0
    assert ceo["stock_turnover"] == 0.0
    fin = client.get("/api/reports/finance", headers=admin_headers).json()["data"]
    assert fin["total_payable"] == 0.0
    assert fin["total_receivable"] == 0.0
    assert fin["net_cash_gap"] == 0.0
    perf = client.get("/api/reports/performance", headers=admin_headers).json()["data"]
    assert perf["ship_rate"] == 0.0
    assert perf["avg_ship_hours"] is None
