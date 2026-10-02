"""数据看板接口测试：指标 / 趋势补齐 / 店铺分布。"""


def test_dashboard_stats(client, admin_headers, operator_headers):
    """造数据：店铺 + 商品 → stats 指标一致且趋势为连续 7 天。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "看板店"}, headers=admin_headers
    ).json()["data"]
    client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": "D-001", "name": "看板商品", "stock": 1, "safety_stock": 10},
        headers=operator_headers,
    )
    # 用 inventory 流水造"出库"不影响订单；订单直接经 ORM 不可行（无写接口），
    # 演示阶段订单由 Mock 数据产生 —— 这里通过前端看板依赖的其余指标验证，
    # 趋势数据为空表时也应返回连续 7 天且 amount=0（关键验收：折线不断）。

    data = client.get("/api/dashboard/stats", headers=admin_headers).json()["data"]
    assert data["total_products"] == 1
    assert data["alert_count"] == 1  # stock=1 < safety=10
    assert data["total_shops"] == 1
    assert len(data["sales_trend"]) == 7  # 连续 7 天，无订单日补 0
    assert all("date" in d and "amount" in d for d in data["sales_trend"])
    assert data["shop_distribution"] == [{"shop": "看板店", "product_count": 1}]
