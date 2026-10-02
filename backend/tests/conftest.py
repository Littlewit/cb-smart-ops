import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, get_db
from app.main import create_app

# 测试统一密码（注册接口要求 >= 6 位）
TEST_PASSWORD = "Passw0rd!"


def make_auth_headers(client: TestClient, username: str, role: str) -> dict:
    """注册 + 登录，返回带 JWT 的请求头（每个测试库独立，用户名可固定）。"""
    resp = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": TEST_PASSWORD,
            "email": f"{username}@test.com",
            "role": role,
        },
    )
    assert resp.status_code == 201, resp.text
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path_factory, monkeypatch):
    """每个测试独享的临时 SQLite 库；NullPool 避免连接跨事件循环复用。

    同时把全局 settings.database_url 指向测试库：
    Celery eager 任务内部用 task_session() 按 settings 现建引擎，
    打补丁后任务与 API 操作同一个库，端到端链路才能在测试中打通。
    """
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    from app.core import database as core_db

    monkeypatch.setattr(core_db.settings, "database_url", db_url)

    engine = create_async_engine(db_url, poolclass=NullPool)
    TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def init_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init_tables())

    async def override_get_db():
        async with TestingSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as test_client:
        yield test_client
    asyncio.run(engine.dispose())


@pytest.fixture
def admin_headers(client):
    return make_auth_headers(client, "admin_user", "admin")


@pytest.fixture
def operator_headers(client):
    return make_auth_headers(client, "operator_user", "operator")


@pytest.fixture
def viewer_headers(client):
    return make_auth_headers(client, "viewer_user", "viewer")
