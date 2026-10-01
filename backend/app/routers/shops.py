"""店铺路由：CRUD（admin）+ 同步触发（operator）+ 连通性测试。

权限矩阵（需求 §3.1 / 设计 §5）：
- 列表/详情：viewer 及以上
- 创建/更新/删除：admin
- 触发同步：operator 及以上
- 连通性测试：admin
"""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import User
from app.schemas import ShopCreate, ShopOut, ShopUpdate
from app.services import shop_service
from app.tasks.sync import sync_shop_task
from app.utils import platform_client

router = APIRouter(prefix="/api/shops", tags=["shops"])


@router.get("")
async def list_shops(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """店铺列表（输出不含凭证字段）。"""
    shops = await shop_service.list_shops(db)
    return ok([ShopOut.model_validate(s).model_dump(mode="json") for s in shops])


@router.post("", status_code=201)
async def create_shop(
    payload: ShopCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """创建店铺：凭证明文仅在此请求中出现一次，落库即加密。"""
    shop = await shop_service.create_shop(db, payload)
    return ok(ShopOut.model_validate(shop).model_dump(mode="json"))


@router.put("/{shop_id}")
async def update_shop(
    shop_id: str,
    payload: ShopUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """更新店铺（部分更新）。"""
    shop = await shop_service.update_shop(db, shop_id, payload)
    return ok(ShopOut.model_validate(shop).model_dump(mode="json"))


@router.delete("/{shop_id}")
async def delete_shop(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """删除店铺。"""
    await shop_service.delete_shop(db, shop_id)
    return ok(message="deleted")


@router.post("/{shop_id}/sync")
async def trigger_sync(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """触发店铺同步（Celery 异步任务），立即返回 task_id。

    注意：to_thread 是必须的 —— 开发阶段 Celery 为 eager 模式，
    delay() 会同步执行任务；任务内部要 asyncio.run()，不能在
    FastAPI 的事件循环线程里调用，因此丢到线程池执行。
    """
    await shop_service.get_shop_or_404(db, shop_id)
    result = await asyncio.to_thread(sync_shop_task.delay, shop_id)
    return ok({"task_id": result.id, "message": "同步已提交"})


@router.post("/{shop_id}/test")
async def test_connection(
    shop_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """连通性测试：尝试拉取一次商品列表，成功则标记 connected。

    异常不抛出（同步任务有自己的重试），而是如实返回 disconnected，
    方便演示"凭证错误/平台不可达"的场景。
    """
    shop = await shop_service.get_shop_or_404(db, shop_id)
    try:
        items = await asyncio.to_thread(platform_client.fetch_products, shop.platform)
        shop.status = "connected"
        return ok({"status": "connected", "product_count": len(items)})
    except Exception:
        shop.status = "disconnected"
        return ok({"status": "disconnected"})
