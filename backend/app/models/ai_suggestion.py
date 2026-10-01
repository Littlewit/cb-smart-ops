from typing import Any, Optional

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class AiSuggestion(BaseMixin, Base):
    """AI 建议：结构化内容存 JSONB（SQLite 下为 JSON），按 type 渲染卡片。"""

    __tablename__ = "ai_suggestions"
    __table_args__ = (Index("ix_ai_suggestions_status", "status"),)

    # restock / pricing / alert
    type: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("products.id"), nullable=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 引用的规则文档 id
    rule_refs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # pending / accepted / dismissed
    status: Mapped[str] = mapped_column(String(20), default="pending")
