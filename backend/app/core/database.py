from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# 全局异步引擎：供 FastAPI 请求使用（请求共享同一事件循环，可安全复用连接池）
engine = create_async_engine(settings.database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI 依赖：请求级数据库会话，成功提交、异常回滚。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def task_session():
    """Celery 任务专用数据库会话（上下文管理器）。

    任务内部使用 asyncio.run() 每次创建新事件循环，而全局 engine 的连接池
    可能持有绑定到旧循环的连接（SQLite/PG 驱动均会出问题）；
    因此每个任务临时创建独立引擎，用完立即释放，规避跨循环复用。
    """
    task_engine = create_async_engine(settings.database_url)
    try:
        async with async_sessionmaker(task_engine, expire_on_commit=False)() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await task_engine.dispose()
