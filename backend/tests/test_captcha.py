"""图形验证码测试：登录强校验、一次性消费、错误码拒绝。"""

import pytest

from app.core import captcha as captcha_mod

pytestmark = pytest.mark.usefixtures("client")


def _issue_and_login(client, username="admin", password="admin123", code=None, captcha_id=None):
    """辅助：签发验证码并尝试登录（code/captcha_id 可覆盖以模拟输错）。"""
    cid, answer, _ = captcha_mod.issue()
    resp = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": password,
            "captcha_id": captcha_id or cid,
            "captcha_code": code if code is not None else answer,
        },
    )
    return resp


def test_captcha_endpoint_returns_image(client):
    """验证码端点：返回 captcha_id 与 base64 PNG data-url。"""
    resp = client.get("/api/auth/captcha")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["captcha_id"]
    assert data["image"].startswith("data:image/png;base64,")


def test_login_without_captcha_rejected(client):
    """不带验证码 → 422（缺必填字段，Pydantic 层拦截，先于业务校验）。"""
    client.post(
        "/api/auth/register",
        json={
            "username": "cap_user",
            "password": "Passw0rd!",
            "email": "cap@test.com",
            "role": "viewer",
        },
    )
    resp = client.post(
        "/api/auth/login", json={"username": "cap_user", "password": "Passw0rd!"}
    )
    assert resp.status_code == 422


def test_login_wrong_captcha_rejected(client):
    """验证码错误 → 400（即使账密正确）。"""
    client.post(
        "/api/auth/register",
        json={
            "username": "cap_user2",
            "password": "Passw0rd!",
            "email": "cap2@test.com",
            "role": "viewer",
        },
    )
    resp = _issue_and_login(client, username="cap_user2", code="XXXX")
    assert resp.status_code == 400


def test_captcha_one_time_use(client):
    """一次性消费：同一 captcha 第二次使用 → 400（防重放）。"""
    client.post(
        "/api/auth/register",
        json={
            "username": "cap_user3",
            "password": "Passw0rd!",
            "email": "cap3@test.com",
            "role": "viewer",
        },
    )
    # 第一次：验证码正确 + 账密正确 → 200
    resp = _issue_and_login(client, username="cap_user3", password="Passw0rd!")
    assert resp.status_code == 200

    # 同一 captcha 重放 → 400
    cid, _, _ = captcha_mod.issue()
    resp = _issue_and_login(client, username="cap_user3", password="Passw0rd!", captcha_id=cid)
    assert resp.status_code == 400
