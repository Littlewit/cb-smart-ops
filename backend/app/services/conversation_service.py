"""会话服务：AI 对话历史的持久化与归属校验。

设计要点：
- 会话与用户绑定（user_id），所有读取都做归属校验，防止越权拉取他人对话
- 消息角色直接使用 OpenAI 命名（user/assistant），回传 LLM 时免转换
- 删除会话时显式先删消息：SQLite 默认不开启外键级联，靠 ORM 端保证
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, Conversation


async def create_conversation(db: AsyncSession, user_id: str, title: str) -> Conversation:
    """新建会话；标题超长截断到 120 字符（与列宽一致）。"""
    conv = Conversation(user_id=user_id, title=title[:120])
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def get_owned_or_404(
    db: AsyncSession, conversation_id: str, user_id: str
) -> Conversation:
    """取会话并校验归属：不存在或非本人 → 404（不区分两种情况，防探测）。"""
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


async def append_message(
    db: AsyncSession, conversation_id: str, role: str, content: str
) -> ChatMessage:
    """追加一条消息（user / assistant 通用）。"""
    msg = ChatMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    return msg


async def load_history(
    db: AsyncSession, conversation_id: str, limit: int = 6
) -> list[dict]:
    """取最近 limit 条消息并转为 OpenAI messages 格式（供 LLM 多轮上下文）。"""
    rows = list(
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    # 倒序取的，翻回正序
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


async def list_conversations(db: AsyncSession, user_id: str) -> list[dict]:
    """用户会话列表（按更新时间倒序，前端侧栏直接渲染）。"""
    rows = list(
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
            )
        ).scalars()
    )
    return [
        {"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat()}
        for c in rows
    ]


async def list_messages(db: AsyncSession, conversation_id: str) -> list[dict]:
    """会话全部消息（正序），用于前端恢复对话气泡。"""
    rows = list(
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at)
            )
        ).scalars()
    )
    return [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in rows
    ]


async def delete_conversation(db: AsyncSession, conversation_id: str) -> None:
    """删除会话：先删消息再删会话（SQLite 未开外键级联，显式双删）。"""
    await db.execute(
        ChatMessage.__table__.delete().where(
            ChatMessage.conversation_id == conversation_id
        )
    )
    conv = await db.get(Conversation, conversation_id)
    if conv is not None:
        await db.delete(conv)
    await db.flush()
