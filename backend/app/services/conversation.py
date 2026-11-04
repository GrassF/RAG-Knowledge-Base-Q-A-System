"""会话与消息持久化：多轮对话记忆的「存储侧」。

职责：创建/列出/改名/删除会话，追加消息，build_history() 取最近 N 轮
      并转成 LangChain 消息对象，供 Prompt 的历史占位符使用
配置：max_history_rounds 控制窗口大小（默认 10 轮 = 20 条消息）
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BizException, ErrorCode
from app.db.models import Conversation, Message, now
from app.schemas.chat import ConversationOut, MessageOut, SourceItem

TITLE_MAX_CHARS = 20


class ConversationService:
    """在已有数据库会话上操作会话数据。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    # ===================== 会话 =====================
    def get_or_create(
        self, conversation_id: str | None, first_question: str
    ) -> Conversation:
        if conversation_id:
            conversation = self.get(conversation_id)
            if conversation.title in ("", "新对话"):
                conversation.title = self._make_title(first_question)
            return conversation

        conversation = Conversation(title=self._make_title(first_question))
        self.db.add(conversation)
        self.db.flush()
        logger.info("新建会话 {}", conversation.id)
        return conversation

    def get(self, conversation_id: str) -> Conversation:
        conversation = self.db.get(Conversation, conversation_id)
        if conversation is None:
            raise BizException(ErrorCode.CONVERSATION_NOT_FOUND)
        return conversation

    def list_all(self) -> list[ConversationOut]:
        rows = self.db.execute(
            select(Conversation, func.count(Message.id))
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc())
        ).all()

        return [
            ConversationOut(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                message_count=count,
            )
            for conversation, count in rows
        ]

    def rename(self, conversation_id: str, title: str) -> ConversationOut:
        conversation = self.get(conversation_id)
        conversation.title = title[:128]
        conversation.updated_at = now()
        self.db.flush()
        return self._to_out(conversation)

    def delete(self, conversation_id: str) -> None:
        conversation = self.get(conversation_id)
        self.db.delete(conversation)
        self.db.flush()

    # ===================== 消息 =====================
    def add_message(
        self,
        conversation: Conversation,
        role: str,
        content: str,
        sources: Sequence[SourceItem] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            sources_json=self._dump_sources(sources),
        )
        self.db.add(message)
        conversation.updated_at = now()
        self.db.flush()
        return message

    def list_messages(self, conversation_id: str) -> list[MessageOut]:
        self.get(conversation_id)
        messages = self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        ).all()
        return [self._to_message_out(message) for message in messages]

    def build_history(self, conversation_id: str) -> list[BaseMessage]:
        """取最近 N 轮历史，供 Prompt 使用。

        只取最近 max_history_rounds*2 条，并对超长消息做截断，控制 token 开销。
        """
        self.get(conversation_id)
        limit = max(2, self.settings.max_history_rounds * 2)
        rows = self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).all()

        history: list[BaseMessage] = []
        for message in reversed(rows):
            content = message.content[: self.settings.max_message_chars]
            if message.role == "user":
                history.append(HumanMessage(content=content))
            elif message.role == "assistant":
                history.append(AIMessage(content=content))
        return history

    # ===================== 内部工具 =====================
    @staticmethod
    def _make_title(question: str) -> str:
        title = " ".join(question.split())
        return title[:TITLE_MAX_CHARS] or "新对话"

    @staticmethod
    def _dump_sources(sources: Sequence[SourceItem] | None) -> str | None:
        if not sources:
            return None
        return json.dumps([item.model_dump() for item in sources], ensure_ascii=False)

    @staticmethod
    def _load_sources(raw: str | None) -> list[SourceItem]:
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        items: list[SourceItem] = []
        for entry in payload:
            try:
                items.append(SourceItem(**entry))
            except Exception:  # 历史数据字段缺失时跳过，不影响整体展示
                continue
        return items

    def _to_message_out(self, message: Message) -> MessageOut:
        return MessageOut(
            id=message.id,
            role=message.role,
            content=message.content,
            sources=self._load_sources(message.sources_json),
            created_at=message.created_at,
        )

    @staticmethod
    def _to_out(conversation: Conversation) -> ConversationOut:
        return ConversationOut(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
