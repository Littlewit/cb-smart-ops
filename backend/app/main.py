from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    return app


app = create_app()
