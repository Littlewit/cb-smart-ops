"""认证与 RBAC 测试：注册/登录/角色权限边界。"""

from app.core import captcha as captcha_mod


def _login(client, username: str, password: str):
    """带图形验证码的登录辅助（测试通过 issue() 获取明文答案）。"""
    captcha_id, captcha_code, _ = captcha_mod.issue()
    return client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": password,
            "captcha_id": captcha_id,
            "captcha_code": captcha_code,
        },
    )


def test_register_and_login(client):
    # 注册 → 201，返回用户信息（不含密码哈希）
    resp = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "password": "Passw0rd!",
            "email": "alice@test.com",
            "role": "operator",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["username"] == "alice"
    assert data["role"] == "operator"
    assert "password" not in data and "password_hash" not in data

    # 登录 → 返回 JWT
    resp = _login(client, "alice", "Passw0rd!")
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


def test_register_duplicate_username(client):
    payload = {
        "username": "bob",
        "password": "Passw0rd!",
        "email": "bob@test.com",
        "role": "viewer",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    # 同名再注册 → 409
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={
            "username": "carol",
            "password": "Passw0rd!",
            "email": "carol@test.com",
            "role": "viewer",
        },
    )
    # 错误密码 → 401（不区分"用户不存在"与"密码错误"，防枚举）
    resp = _login(client, "carol", "Wrong999!")
    assert resp.status_code == 401


def test_reset_password_flow(client):
    """忘记密码：用户名+邮箱 匹配重置 → 新密码可登录、旧密码失效；不匹配 → 400。"""
    client.post(
        "/api/auth/register",
        json={
            "username": "dave",
            "password": "Passw0rd!",
            "email": "dave@test.com",
            "role": "viewer",
        },
    )

    # 邮箱不匹配 → 400（统一文案防枚举）
    resp = client.post(
        "/api/auth/reset-password",
        json={"username": "dave", "email": "wrong@test.com", "new_password": "New99999!"},
    )
    assert resp.status_code == 400

    # 匹配 → 重置成功
    resp = client.post(
        "/api/auth/reset-password",
        json={"username": "dave", "email": "dave@test.com", "new_password": "New99999!"},
    )
    assert resp.status_code == 200

    # 旧密码失效、新密码可登录
    assert _login(client, "dave", "Passw0rd!").status_code == 401
    assert _login(client, "dave", "New99999!").status_code == 200


def test_change_password_requires_old_password(client, operator_headers):
    """已登录修改密码：旧密码错 → 400；正确 → 新密码可登录。"""
    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": "Wrong999!", "new_password": "New88888!"},
        headers=operator_headers,
    )
    assert resp.status_code == 400

    resp = client.post(
        "/api/auth/change-password",
        json={"old_password": "Passw0rd!", "new_password": "New88888!"},
        headers=operator_headers,
    )
    assert resp.status_code == 200

    # 新密码登录成功（注意：旧 JWT 仍有效至过期，无黑名单机制，演示级取舍）
    resp = _login(client, "operator_user", "New88888!")
    assert resp.status_code == 200


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
