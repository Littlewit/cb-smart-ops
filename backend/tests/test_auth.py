"""认证与 RBAC 测试：注册/登录/角色权限边界。"""


def test_register_and_login(client):
    # 注册 → 201，返回用户信息（不含密码哈希）
    resp = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "Passw0rd!", "role": "operator"},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["username"] == "alice"
    assert data["role"] == "operator"
    assert "password" not in data and "password_hash" not in data

    # 登录 → 返回 JWT
    resp = client.post(
        "/api/auth/login", json={"username": "alice", "password": "Passw0rd!"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


def test_register_duplicate_username(client):
    payload = {"username": "bob", "password": "Passw0rd!", "role": "viewer"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    # 同名再注册 → 409
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={"username": "carol", "password": "Passw0rd!", "role": "viewer"},
    )
    # 错误密码 → 401（不区分"用户不存在"与"密码错误"，防枚举）
    resp = client.post(
        "/api/auth/login", json={"username": "carol", "password": "Wrong999!"}
    )
    assert resp.status_code == 401


def test_rbac_permission_matrix(client, admin_headers, operator_headers, viewer_headers):
    """权限矩阵抽查：viewer 只读、operator 可操作商品、admin 管店铺。"""
    # 未认证访问受保护接口 → 401
    assert client.get("/api/shops").status_code == 401

    # viewer 不能创建店铺（403）
    resp = client.post(
        "/api/shops",
        json={"platform": "mock", "name": "v店"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403

    # viewer 不能创建商品（403）
    resp = client.post(
        "/api/products",
        json={"shop_id": "x", "sku": "S1", "name": "n"},
        headers=viewer_headers,
    )
    assert resp.status_code == 403

    # operator 不能创建店铺（403，店铺管理是 admin 专属）
    resp = client.post(
        "/api/shops",
        json={"platform": "mock", "name": "o店"},
        headers=operator_headers,
    )
    assert resp.status_code == 403

    # admin 可以创建店铺（201）
    resp = client.post(
        "/api/shops",
        json={"platform": "mock", "name": "a店", "credentials": "secret"},
        headers=admin_headers,
    )
    assert resp.status_code == 201

    # viewer 可以读店铺列表（只读放行）
    resp = client.get("/api/shops", headers=viewer_headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
