from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseMixin


class RuleDocument(BaseMixin, Base):
    """RAG 运营规则文档（滞销品定义、补货公式等）。

    embedding 向量列仅在 PostgreSQL（pgvector）下存在，SQLite 开发期不建列，
    切换 PG 时通过 Alembic 迁移补充（见系统设计文档 §3）。
    """

    __tablename__ = "rule_documents"

    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
