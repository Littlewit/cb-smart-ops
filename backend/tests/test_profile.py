"""个人中心接口测试：GET/PUT /api/auth/me（信息展示与邮箱更新）。"""


def test_get_profile(client, admin_headers):
    """登录后拉取个人信息：字段齐全且与注册时一致。"""
    resp = client.get("/api/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    # conftest 固定用户名 admin_user，邮箱按用户名生成
    assert data["username"] == "admin_user"
    assert data["role"] == "admin"
    assert data["email"] == "admin_user@test.com"
    assert data["created_at"]


def test_update_profile_email(client, admin_headers):
    """更新邮箱 → 返回新值且 GET /me 一致（忘记密码匹配依据随之生效）。"""
    resp = client.put(
        "/api/auth/me", json={"email": "newmail@example.com"}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "newmail@example.com"

    data = client.get("/api/auth/me", headers=admin_headers).json()["data"]
    assert data["email"] == "newmail@example.com"


def test_update_profile_rejects_bad_email(client, admin_headers):
    """非法邮箱格式 → 422（pydantic pattern 校验）。"""
    resp = client.put(
        "/api/auth/me", json={"email": "not-an-email"}, headers=admin_headers
    )
    assert resp.status_code == 422


def test_profile_requires_login(client):
    """未登录访问 /me → 401（个人中心不设公开访问）。"""
    assert client.get("/api/auth/me").status_code == 401
    assert client.put("/api/auth/me", json={"email": "x@example.com"}).status_code == 401
