"""运营规则知识库业务：RAG 规则文档的 CRUD（管理界面数据源）。

规则变更立即影响 RAG 检索（rag.retrieve_rules 实时查库，无缓存）；
删除规则后对应检索结果消失，内置规则兜底不受影响。
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RuleDocument


async def list_rules(db: AsyncSession) -> list[RuleDocument]:
    """规则全量列表（知识库量级小，不分页）。"""
    return list(
        (await db.execute(select(RuleDocument).order_by(RuleDocument.created_at))).scalars()
    )


async def create_rule(db: AsyncSession, title: str, content: str) -> RuleDocument:
    """新增规则：标题唯一冲突 409（前端以标题作为规则标识展示）。"""
    dup = (
        await db.execute(select(RuleDocument).where(RuleDocument.title == title))
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "规则标题已存在")
    rule = RuleDocument(title=title, content=content)
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


async def update_rule(db: AsyncSession, rule_id: str, title: str, content: str) -> RuleDocument:
    """更新规则（标题/内容全量提交）。"""
    rule = await db.get(RuleDocument, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    dup = (
        await db.execute(
            select(RuleDocument).where(RuleDocument.title == title, RuleDocument.id != rule_id)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "规则标题已存在")
    rule.title = title
    rule.content = content
    await db.flush()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, rule_id: str) -> None:
    """删除规则（RAG 检索实时生效）。"""
    rule = await db.get(RuleDocument, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    await db.delete(rule)
    await db.flush()
