"""问答编排 + SSE 事件流。

一次问答的事件顺序（前端据此渲染）：
    meta    -> 会话信息（新建会话时前端需要拿到 id）
    sources -> 本次回答引用的片段列表（文件名 / 页码 / 章节 / 分数）
    delta   -> 答案 token（多次）
    done    -> 落库后的消息 id 与耗时
    error   -> 任何阶段失败

之所以不用 RunnableWithMessageHistory 一把梭：来源卡片必须在答案之前
先推给前端，需要把"检索"和"生成"两步拆开控制。
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from loguru import logger

from app.core.exceptions import BizException, ErrorCode
from app.db.database import session_scope
from app.schemas.chat import ChatRequest, RetrievalOptions
from app.services.conversation import ConversationService
from app.services.rag_chain import RagChain


def sse_event(event: str, data: Any) -> str:
    """按 SSE 协议拼一条事件。data 统一 JSON 编码，避免换行打断消息边界。"""
    if isinstance(data, str):
        data = {"text": data}
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class ChatService:
    def __init__(self, rag: RagChain) -> None:
        self.rag = rag

    def stream_chat(
        self, user_id: int, request: ChatRequest, conversation_id: str | None = None
    ) -> Iterator[str]:
        """产出 SSE 文本块。自带数据库会话，与请求级会话解耦。"""
        started_at = time.perf_counter()
        options: RetrievalOptions | None = request.retrieval

        with session_scope() as db:
            conversations = ConversationService(db)
            conversation = conversations.get_or_create(
                user_id=user_id,
                conversation_id=conversation_id or request.conversation_id,
                first_question=request.question,
            )
            conversation_id = conversation.id
            title = conversation.title

            yield sse_event("meta", {"conversation_id": conversation_id, "title": title})

            history = conversations.build_history(conversation_id, user_id)
            conversations.add_message(conversation, "user", request.question)

            # ---------- 1. 检索 ----------
            try:
                search_query = self.rag.rewrite_query(request.question, history)
                chunks = self.rag.retrieve(search_query, options)
            except BizException as exc:
                logger.warning("检索失败：{}", exc.message)
                yield sse_event("error", {"code": exc.code, "message": exc.message})
                return
            except Exception as exc:  # 兜底，避免连接悬挂
                logger.exception("检索阶段异常")
                yield sse_event(
                    "error", {"code": ErrorCode.INDEX_ERROR.code, "message": f"检索失败：{exc}"}
                )
                return

            sources = [chunk.to_source(index) for index, chunk in enumerate(chunks, start=1)]
            yield sse_event(
                "sources",
                {
                    "sources": [item.model_dump() for item in sources],
                    "search_query": search_query,
                },
            )

            # ---------- 2. 生成 ----------
            answer_parts: list[str] = []
            try:
                for delta in self.rag.stream_answer(request.question, chunks, history):
                    answer_parts.append(delta)
                    yield sse_event("delta", {"text": delta})
            except Exception as exc:
                logger.exception("生成阶段异常")
                yield sse_event(
                    "error", {"code": ErrorCode.LLM_ERROR.code, "message": f"生成失败：{exc}"}
                )
                return

            # ---------- 3. 落库 ----------
            answer = "".join(answer_parts).strip()
            message = conversations.add_message(
                conversation, "assistant", answer, sources=sources
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            yield sse_event(
                "done",
                {
                    "message_id": message.id,
                    "conversation_id": conversation_id,
                    "conversation_title": title,
                    "latency_ms": latency_ms,
                    "source_count": len(sources),
                },
            )
            logger.info(
                "问答完成：conversation={} chunks={} 答案长度={} 耗时={}ms",
                conversation_id,
                len(sources),
                len(answer),
                latency_ms,
            )
