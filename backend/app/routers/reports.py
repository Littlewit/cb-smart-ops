"""报表路由：CEO 看板 / 运营绩效 / 财务对账（只读聚合，viewer 可见）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import User
from app.services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/ceo")
async def ceo_dashboard(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    days: int = Query(default=30, ge=7, le=90),
):
    """CEO 看板：GMV / 毛利 / 库存周转 / 预警数 + 销售趋势。"""
    return ok(await report_service.ceo_dashboard(db, days))


@router.get("/performance")
async def operation_performance(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
):
    """运营绩效：发货漏斗 / 发货时效 / 预警处理。"""
    return ok(await report_service.operation_performance(db))


@router.get("/finance")
async def finance_reconciliation(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    days: int = Query(default=30, ge=7, le=90),
):
    """财务对账：采购应付 vs 销售应收（按供应商/平台分组）。"""
    return ok(await report_service.finance_reconciliation(db, days))
