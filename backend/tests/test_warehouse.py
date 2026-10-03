"""仓库模块测试：批次列表 / 库位 CRUD / 盘点闭环（差异写账实分离流水）。"""


def _setup(client, admin_headers, operator_headers):
    """前置：店铺+商品(stock=10, safety=5) + 一个库位。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "仓库测试店"}, headers=admin_headers
    ).json()["data"]
    product = client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": "WH-001", "name": "仓库商品", "stock": 10, "safety_stock": 5},
        headers=operator_headers,
    ).json()["data"]
    loc = client.post(
        "/api/warehouse/locations", json={"code": "A-01-01", "name": "A 区"}, headers=operator_headers
    ).json()["data"]
    return shop, product, loc


def test_location_crud(client, admin_headers, operator_headers):
    """库位：创建/重名 409/列表。"""
    _setup(client, admin_headers, operator_headers)
    resp = client.post(
        "/api/warehouse/locations", json={"code": "B-02-01"}, headers=operator_headers
    )
    assert resp.status_code == 201
    # 重名
    assert (
        client.post("/api/warehouse/locations", json={"code": "B-02-01"}, headers=operator_headers).status_code
        == 409
    )
    data = client.get("/api/warehouse/locations", headers=admin_headers).json()["data"]
    assert data["total"] == 2


def test_stocktaking_full_cycle(client, admin_headers, operator_headers):
    """盘点闭环：创建快照 → 录入实盘 → 提交差异入账 → 批次/余额同步。"""
    _, product, loc = _setup(client, admin_headers, operator_headers)

    # 创建盘点单（快照 system_qty=10）
    st = client.post("/api/warehouse/stocktakings", headers=operator_headers).json()["data"]
    assert st["item_count"] == 1
    detail = client.get(f"/api/warehouse/stocktakings/{st['id']}", headers=operator_headers).json()["data"]
    item = detail["items"][0]
    assert item["system_qty"] == 10

    # 录入实盘 7（盘亏 -3）
    resp = client.put(
        f"/api/warehouse/stocktakings/{st['id']}/items/{item['id']}",
        json={"counted_qty": 7},
        headers=operator_headers,
    )
    assert resp.json()["data"]["diff_qty"] == -3

    # 提交盘点：余额 10 → 7（check 流水），差异项计入调整
    resp = client.post(
        f"/api/warehouse/stocktakings/{st['id']}/complete", headers=operator_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["adjusted_count"] == 1

    data = client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["data"]
    assert data["stock"] == 7

    # 流水出现 check 记录
    logs = client.get(
        f"/api/inventory/logs?product_id={product['id']}", headers=admin_headers
    ).json()["data"]
    assert any(l["type"] == "check" for l in logs["items"])

    # 已提交不可再录入
    resp = client.put(
        f"/api/warehouse/stocktakings/{st['id']}/items/{item['id']}",
        json={"counted_qty": 10},
        headers=operator_headers,
    )
    assert resp.status_code == 400


def test_batches_list(client, admin_headers, operator_headers):
    """批次列表接口可查询（空列表 + 结构正确）。"""
    _setup(client, admin_headers, operator_headers)
    data = client.get("/api/warehouse/batches", headers=admin_headers).json()["data"]
    assert isinstance(data["items"], list)
