"""商品业务：CRUD / 多平台 SKU 映射 / 预警状态维护。

预警规则：stock < safety_stock 即标记 alert_status=True（需求 FR-2.2）。
任何会改变 stock 或 safety_stock 的路径都必须调用 _refresh_alert。
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiSuggestion, InventoryLog, Product, ProductSkuMapping, Shop
from app.schemas import ProductCreate, ProductUpdate, SkuMappingCreate


async def get_product_or_404(db: AsyncSession, product_id: str) -> Product:
    """按 ID 取商品，不存在则抛 404。"""
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "商品不存在")
    return product


def _refresh_alert(product: Product) -> None:
    """根据当前库存与安全库存刷新预警状态（内存对象上的同步计算）。"""
    product.alert_status = product.stock < product.safety_stock


async def create_product(db: AsyncSession, payload: ProductCreate) -> Product:
    """创建商品：店铺必须存在；同店铺内 SKU 唯一。"""
    if await db.get(Shop, payload.shop_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "店铺不存在")

    exists = await db.execute(
        select(Product).where(Product.shop_id == payload.shop_id, Product.sku == payload.sku)
    )
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "同店铺下 SKU 已存在")

    product = Product(**payload.model_dump())
    _refresh_alert(product)
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def update_product(db: AsyncSession, product_id: str, payload: ProductUpdate) -> Product:
    """部分更新商品；stock/safety_stock 变化后自动刷新预警状态。"""
    product = await get_product_or_404(db, product_id)
    data = payload.model_dump(exclude_none=True)
    for field, value in data.items():
        setattr(product, field, value)
    _refresh_alert(product)
    await db.flush()
    await db.refresh(product)
    return product


async def delete_product(db: AsyncSession, product_id: str) -> None:
    """删除商品：先清理关联数据（SKU 映射/库存流水/AI 建议），再删商品本身。"""
    product = await get_product_or_404(db, product_id)

    # 演示项目直接物理删除关联数据；生产环境应改为归档/软删
    for model, field in (
        (ProductSkuMapping, ProductSkuMapping.product_id),
        (InventoryLog, InventoryLog.product_id),
        (AiSuggestion, AiSuggestion.product_id),
    ):
        for row in (await db.execute(select(model).where(field == product_id))).scalars():
            await db.delete(row)

    await db.delete(product)
    await db.flush()


# ---------- 多平台 SKU 映射 ----------

async def add_sku_mapping(
    db: AsyncSession, product_id: str, payload: SkuMappingCreate
) -> ProductSkuMapping:
    """为商品添加平台侧 SKU 映射；(platform, external_sku) 全局唯一。"""
    await get_product_or_404(db, product_id)
    exists = await db.execute(
        select(ProductSkuMapping).where(
            ProductSkuMapping.platform == payload.platform,
            ProductSkuMapping.external_sku == payload.external_sku,
        )
    )
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "该平台 SKU 已被映射")

    mapping = ProductSkuMapping(product_id=product_id, **payload.model_dump())
    db.add(mapping)
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def delete_sku_mapping(db: AsyncSession, product_id: str, mapping_id: str) -> None:
    """删除一条 SKU 映射（校验归属，防止跨商品删除）。"""
    mapping = await db.get(ProductSkuMapping, mapping_id)
    if mapping is None or mapping.product_id != product_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SKU 映射不存在")
    await db.delete(mapping)
    await db.flush()
