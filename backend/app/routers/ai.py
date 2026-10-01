"""AI 路由（Day2 先提供建议列表；Day3 接入 DeepSeek 补齐 advice/chat）。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models import AiSuggestion, User

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/suggestions")
async def list_suggestions(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("viewer")),
    product_id: Optional[str] = Query(default=None, description="按商品过滤"),
    status: Optional[str] = Query(default=None, description="pending/accepted/dismissed"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """AI 建议分页列表，前端按 type 渲染建议卡片。"""
    query = select(AiSuggestion).order_by(AiSuggestion.created_at.desc())
    count_query = select(func.count(AiSuggestion.id))
    if product_id:
        query, count_query = query.where(AiSuggestion.product_id == product_id), (
            count_query.where(AiSuggestion.product_id == product_id)
        )
    if status:
        query, count_query = query.where(AiSuggestion.status == status), count_query.where(
            AiSuggestion.status == status
        )

    total = (await db.execute(count_query)).scalar_one()
    items = list(
        (
            await db.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).scalars()
        .all()
    )
    return ok(
        {
            "items": [
                {
                    "id": s.id,
                    "type": s.type,
                    "product_id": s.product_id,
                    "content": s.content,
                    "rule_refs": s.rule_refs,
                    "status": s.status,
                    "created_at": s.created_at.isoformat(),
                }
                for s in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
