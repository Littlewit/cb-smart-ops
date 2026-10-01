"""店铺业务：CRUD / 凭证加密存储 / 同步与连通性测试。

凭证安全约定：明文只在 create/update 请求中出现一次，立即加密落库；
服务层返回的 Shop 对象可以带密文，但接口层输出 Schema 永不包含凭证字段。
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import Shop
from app.schemas import ShopCreate, ShopUpdate


async def get_shop_or_404(db: AsyncSession, shop_id: str) -> Shop:
    """按 ID 取店铺，不存在则抛 404。"""
    shop = await db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "店铺不存在")
    return shop


async def list_shops(db: AsyncSession) -> list[Shop]:
    """店铺列表（按创建时间倒序）。"""
    return list(
        (await db.execute(select(Shop).order_by(Shop.created_at.desc()))).scalars().all()
    )


async def create_shop(db: AsyncSession, payload: ShopCreate) -> Shop:
    """创建店铺：同平台店铺名唯一；凭证明文立即加密。"""
    exists = await db.execute(
        select(Shop).where(Shop.platform == payload.platform, Shop.name == payload.name)
    )
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "同平台下店铺名已存在")

    shop = Shop(
        platform=payload.platform,
        name=payload.name,
        credentials_enc=security.encrypt_credentials(payload.credentials)
        if payload.credentials
        else None,
        status="active",
    )
    db.add(shop)
    await db.flush()
    await db.refresh(shop)
    return shop


async def update_shop(db: AsyncSession, shop_id: str, payload: ShopUpdate) -> Shop:
    """部分更新店铺；传入 credentials 则重新加密。"""
    shop = await get_shop_or_404(db, shop_id)
    if payload.name is not None:
        shop.name = payload.name
    if payload.status is not None:
        shop.status = payload.status
    if payload.credentials is not None:
        shop.credentials_enc = security.encrypt_credentials(payload.credentials)
    await db.flush()
    await db.refresh(shop)
    return shop


async def delete_shop(db: AsyncSession, shop_id: str) -> None:
    """删除店铺（演示项目直接物理删除；不做级联校验，商品须先清理）。"""
    shop = await get_shop_or_404(db, shop_id)
    await db.delete(shop)
    await db.flush()
