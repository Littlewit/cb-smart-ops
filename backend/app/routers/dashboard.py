"""数据看板路由：聚合指标与图表数据（viewer 只读）。"""

from fastapi import APIRouter, Depends
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
):
    """看板统计：指标卡片 + 近7天销售趋势 + 店铺商品分布。"""
    return ok(await dashboard_service.stats(db))
