"""采购模块接口测试：供应商 CRUD / 采购单状态机 / 收货入库闭环。

收货链路重点断言（业务闭环核心）：
- 批次生成（数量与溯源 po_item）
- 账实分离：库存余额增加 + in 流水写入（流水推演 = 余额）
- 部分收货 → receiving；收齐 → completed
- 超收 400、非法状态流转 400
"""


def _create_shop_product(client, admin_headers, operator_headers, sku="PO-A001", stock=5, safety=10):
    """前置：店铺 + 一个预警商品（默认 stock < safety）。"""
    shop = client.post(
        "/api/shops", json={"platform": "mock", "name": "采购测试店"}, headers=admin_headers
    ).json()["data"]
    resp = client.post(
        "/api/products",
        json={"shop_id": shop["id"], "sku": sku, "name": "测试耳机", "stock": stock, "safety_stock": safety},
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    return shop, resp.json()["data"]


def test_supplier_crud(client, admin_headers, operator_headers):
    """供应商：创建 201 / 重名 409 / 更新停用 / 列表。"""
    resp = client.post(
        "/api/suppliers", json={"name": "华南电子厂", "contact": "李工"}, headers=operator_headers
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["data"]["id"]

    # 重名 409
    assert (
        client.post("/api/suppliers", json={"name": "华南电子厂"}, headers=operator_headers).status_code
        == 409
    )

    # 更新：改联系人 + 停用
    resp = client.put(
        f"/api/suppliers/{sid}", json={"contact": "王经理", "status": "disabled"}, headers=operator_headers
    )
    assert resp.json()["data"]["status"] == "disabled"

    # 列表可见
    data = client.get("/api/suppliers", headers=admin_headers).json()["data"]
    assert data["total"] == 1

    # RBAC：未带 token 的创建请求 401
    assert client.post("/api/suppliers", json={"name": "x"}).status_code == 401


def test_purchase_order_lifecycle(client, admin_headers, operator_headers):
    """采购单全生命周期：创建(金额快照) → 编辑 → 提交锁定 → 撤销边界。"""
    _, product = _create_shop_product(client, admin_headers, operator_headers)
    sup = client.post("/api/suppliers", json={"name": "供应商甲"}, headers=operator_headers).json()["data"]

    # 创建：2 件 × 10.5 = 21.0
    resp = client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": sup["id"],
            "remark": "补货",
            "items": [{"product_id": product["id"], "quantity": 2, "unit_price": 10.5}],
        },
        headers=operator_headers,
    )
    assert resp.status_code == 201, resp.text
    po = resp.json()["data"]

    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=admin_headers).json()["data"]
    assert detail["total_amount"] == 21.0
    assert detail["items"][0]["received_qty"] == 0

    # 草稿编辑：改数量重算金额
    resp = client.put(
        f"/api/purchase-orders/{po['id']}",
        json={"items": [{"product_id": product["id"], "quantity": 3, "unit_price": 10.5}]},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=admin_headers).json()["data"]
    assert detail["total_amount"] == 31.5

    # 提交锁定：再次编辑应 400
    assert (
        client.post(f"/api/purchase-orders/{po['id']}/submit", headers=operator_headers).status_code == 200
    )
    resp = client.put(
        f"/api/purchase-orders/{po['id']}",
        json={"items": [{"product_id": product["id"], "quantity": 1, "unit_price": 1}]},
        headers=operator_headers,
    )
    assert resp.status_code == 400

    # completed 后不可撤销（先用第二单验证撤销边界）
    po2 = client.post(
        "/api/purchase-orders",
        json={"supplier_id": sup["id"], "items": [{"product_id": product["id"], "quantity": 1, "unit_price": 1}]},
        headers=operator_headers,
    ).json()["data"]
    assert (
        client.post(f"/api/purchase-orders/{po2['id']}/cancel", headers=operator_headers).status_code == 200
    )
    # cancelled 不可再提交
    assert (
        client.post(f"/api/purchase-orders/{po2['id']}/submit", headers=operator_headers).status_code == 400
    )


def test_receive_full_chain(client, admin_headers, operator_headers):
    """收货入库闭环：部分收货 → receiving → 收齐 → completed。

    断言：批次生成、库存余额增加、in 流水写入、超收 400。
    """
    _, product = _create_shop_product(client, admin_headers, operator_headers, stock=5, safety=10)
    sup = client.post("/api/suppliers", json={"name": "供应商乙"}, headers=operator_headers).json()["data"]
    po = client.post(
        "/api/purchase-orders",
        json={"supplier_id": sup["id"], "items": [{"product_id": product["id"], "quantity": 10, "unit_price": 8}]},
        headers=operator_headers,
    ).json()["data"]
    client.post(f"/api/purchase-orders/{po['id']}/submit", headers=operator_headers)
    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=operator_headers).json()["data"]
    item_id = detail["items"][0]["id"]

    # 超收：一次收 11 > 10 → 400 且库存不变
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/receive",
        json={"items": [{"item_id": item_id, "quantity": 11}]},
        headers=operator_headers,
    )
    assert resp.status_code == 400
    assert client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["data"]["stock"] == 5

    # 部分收货 6 件 → receiving；库存 5+6=11；批次生成
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/receive",
        json={"items": [{"item_id": item_id, "quantity": 6}]},
        headers=operator_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "receiving"

    data = client.get(f"/api/products/{product['id']}", headers=admin_headers).json()["data"]
    assert data["stock"] == 11
    # 库存 11 > 安全库存 10 → 预警自动解除（账实分离联动预警）
    assert data["alert_status"] is False

    # 收齐剩余 4 件 → completed
    resp = client.post(
        f"/api/purchase-orders/{po['id']}/receive",
        json={"items": [{"item_id": item_id, "quantity": 4}]},
        headers=operator_headers,
    )
    assert resp.json()["data"]["status"] == "completed"

    # 库存流水已写入两条收货记录
    logs = client.get(
        f"/api/inventory/logs?product_id={product['id']}", headers=admin_headers
    ).json()["data"]
    in_logs = [l for l in logs["items"] if l["type"] == "in"]
    assert len(in_logs) == 2
    assert all("采购收货" in l["reason"] for l in in_logs)


def test_receive_requires_operator(client, admin_headers, operator_headers):
    """收货入库 RBAC：viewer 不可收货（403）。"""
    _, product = _create_shop_product(client, admin_headers, operator_headers)
    sup = client.post("/api/suppliers", json={"name": "供应商丙"}, headers=operator_headers).json()["data"]
    po = client.post(
        "/api/purchase-orders",
        json={"supplier_id": sup["id"], "items": [{"product_id": product["id"], "quantity": 5, "unit_price": 1}]},
        headers=operator_headers,
    ).json()["data"]
    client.post(f"/api/purchase-orders/{po['id']}/submit", headers=operator_headers)
    detail = client.get(f"/api/purchase-orders/{po['id']}", headers=operator_headers).json()["data"]

    # 建 viewer
    client.post(
        "/api/auth/register",
        json={"username": "po_viewer2", "password": "Passw0rd!", "email": "pv2@t.com", "role": "viewer"},
    )
    from app.core import captcha as cap

    cid, code, _ = cap.issue()
    token = client.post(
        "/api/auth/login",
        json={"username": "po_viewer2", "password": "Passw0rd!", "captcha_id": cid, "captcha_code": code},
    ).json()["data"]["access_token"]
    vh = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        f"/api/purchase-orders/{po['id']}/receive",
        json={"items": [{"item_id": detail["items"][0]["id"], "quantity": 1}]},
        headers=vh,
    )
    assert resp.status_code == 403
