"""商品路由：CRUD（operator+ 写）+ 多平台 SKU 映射。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import Product, ProductSkuMapping, User
from app.schemas import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    SkuMappingCreate,
    SkuMappingOut,
)
from app.services import product_service

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("")
async def list_products(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    q: Optional[str] = Query(default=None, description="按 SKU/名称模糊搜索"),
    shop_id: Optional[str] = Query(default=None, description="按店铺过滤"),
    alert: Optional[bool] = Query(default=None, description="仅看预警商品"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """商品分页列表：支持 SKU/名称搜索、店铺过滤、预警过滤。"""
    query = select(Product).order_by(Product.created_at.desc())
    count_query = select(func.count(Product.id))
    # 三个过滤条件同时拼到列表查询与计数查询上，保证 total 一致
    if q:
        like = f"%{q}%"
        cond = or_(Product.sku.like(like), Product.name.like(like))
        query, count_query = query.where(cond), count_query.where(cond)
    if shop_id:
        query, count_query = query.where(Product.shop_id == shop_id), count_query.where(
            Product.shop_id == shop_id
        )
    if alert is not None:
        cond = Product.alert_status.is_(alert)
        query, count_query = query.where(cond), count_query.where(cond)

    total = (await db.execute(count_query)).scalar_one()
    items = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
        .all()
    )
    return ok(
        {
            "items": [ProductOut.model_validate(p).model_dump(mode="json") for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """商品详情。"""
    product = await product_service.get_product_or_404(db, product_id)
    return ok(ProductOut.model_validate(product).model_dump(mode="json"))


@router.post("", status_code=201)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """创建商品（同店铺 SKU 唯一）。"""
    product = await product_service.create_product(db, payload)
    return ok(ProductOut.model_validate(product).model_dump(mode="json"))


@router.put("/{product_id}")
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """更新商品（部分更新，库存变化自动刷新预警）。"""
    product = await product_service.update_product(db, product_id, payload)
    return ok(ProductOut.model_validate(product).model_dump(mode="json"))


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """删除商品（级联清理 SKU 映射/流水/建议）。"""
    await product_service.delete_product(db, product_id)
    return ok(message="deleted")


# ---------- 多平台 SKU 映射 ----------

@router.get("/{product_id}/sku-mappings")
async def list_sku_mappings(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """查看商品的多平台 SKU 映射列表。"""
    await product_service.get_product_or_404(db, product_id)
    mappings = list(
        (
            await db.execute(
                select(ProductSkuMapping).where(ProductSkuMapping.product_id == product_id)
            )
        )
        .scalars()
        .all()
    )
    return ok([SkuMappingOut.model_validate(m).model_dump(mode="json") for m in mappings])


@router.post("/{product_id}/sku-mappings", status_code=201)
async def add_sku_mapping(
    product_id: str,
    payload: SkuMappingCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """添加 SKU 映射（平台侧 SKU 全局唯一）。"""
    mapping = await product_service.add_sku_mapping(db, product_id, payload)
    return ok(SkuMappingOut.model_validate(mapping).model_dump(mode="json"))


@router.delete("/{product_id}/sku-mappings/{mapping_id}")
async def delete_sku_mapping(
    product_id: str,
    mapping_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("operator")),
):
    """删除 SKU 映射。"""
    await product_service.delete_sku_mapping(db, product_id, mapping_id)
    return ok(message="deleted")
