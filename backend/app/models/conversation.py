from typing import Literal, Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import BaseMixin


class Conversation(BaseMixin, Base):
    """AI 对话会话：刷新/换设备后可恢复历史（方案 B，后端持久化）。

    title 取首条用户消息前 30 字，用于前端会话列表展示。
    """

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user", "user_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120), default="新对话")

    # 主从关系：删除会话时级联删除消息（ORM 级 cascade，见 service 显式删除）
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(BaseMixin, Base):
    """对话消息：user/assistant 各存一条，content 为完整文本。"""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_conversation", "conversation_id"),)

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id")
    )
    # "user" / "assistant"（与 OpenAI messages 角色命名一致，回传 LLM 免转换）
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    # 流式中断标记：True 表示该条 assistant 消息不完整（客户端断开），仅供排查
    truncated: Mapped[Optional[bool]] = mapped_column(default=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    # 角色字面量约束（仅提示作用，DB 层不校验）
    Role = Literal["user", "assistant"]
