"""店铺业务：CRUD / 凭证加密存储 / 同步与连通性测试。

凭证安全约定：明文只在 create/update 请求中出现一次，立即加密落库；
服务层返回的 Shop 对象可以带密文，但接口层输出 Schema 永不包含凭证字段。
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.models import AiSuggestion, InventoryLog, Product, ProductSkuMapping, Shop
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
    """部分更新店铺；传入 credentials 则重新加密。

    重名校验：改名撞同平台已有店铺名时返回 409，
    避免落到数据库唯一约束变成 500。
    """
    shop = await get_shop_or_404(db, shop_id)
    if payload.name is not None and payload.name != shop.name:
        exists = await db.execute(
            select(Shop).where(
                Shop.platform == shop.platform,
                Shop.name == payload.name,
                Shop.id != shop_id,
            )
        )
        if exists.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "同平台下店铺名已存在")
        shop.name = payload.name
    if payload.status is not None:
        shop.status = payload.status
    if payload.credentials is not None:
        shop.credentials_enc = security.encrypt_credentials(payload.credentials)
    await db.flush()
    await db.refresh(shop)
    return shop


async def delete_shop(db: AsyncSession, shop_id: str) -> None:
    """删除店铺：级联清理其下商品及商品的 SKU 映射/库存流水/AI 建议。

    级联是必须的：PG 部署下外键约束会因孤儿商品直接抛 IntegrityError（500），
    SQLite 开发期不启用外键检查所以掩盖了该问题。
    """
    shop = await get_shop_or_404(db, shop_id)

    product_ids = (
        await db.execute(select(Product.id).where(Product.shop_id == shop_id))
    ).scalars().all()
    if product_ids:
        # 先删孙子表（映射/流水/建议），再删商品，最后删店铺
        for model, field in (
            (ProductSkuMapping, ProductSkuMapping.product_id),
            (InventoryLog, InventoryLog.product_id),
            (AiSuggestion, AiSuggestion.product_id),
        ):
            for row in (
                await db.execute(select(model).where(field.in_(product_ids)))
            ).scalars():
                await db.delete(row)
        for row in (
            await db.execute(select(Product).where(Product.shop_id == shop_id))
        ).scalars():
            await db.delete(row)

    await db.delete(shop)
    await db.flush()
