"""数据看板路由：聚合指标与图表数据（viewer 只读）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    days: int = Query(default=7, ge=7, le=90, description="销售趋势天数"),
):
    """看板统计：指标卡片 + 近 N 天销售趋势 + 店铺商品分布。"""
    return ok(await dashboard_service.stats(db, days=days))
