from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.routers import ai, auth, dashboard, health, inventory, products, shops


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 表结构由 Alembic 迁移管理（backend/alembic/），应用启动不做建表
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="跨境电商 AI 辅助运营系统",
        description="多店铺商品同步 / 库存预警 + AI 补货建议 / 运营数据看板",
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(shops.router)
    app.include_router(products.router)
    app.include_router(inventory.router)
    app.include_router(ai.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
