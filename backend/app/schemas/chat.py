"""对话相关的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetrievalOptions(BaseModel):
    """检索参数覆盖。不传则全部使用配置默认值。

    这套参数化也是后续做效果评估（对比 Top-K / 纯向量 vs 混合）的入口。
    """

    mode: Literal["vector", "bm25", "hybrid"] | None = Field(
        default=None, description="检索模式，默认取配置 retrieval_mode"
    )
    top_k: int | None = Field(default=None, ge=1, le=20, description="最终送入 Prompt 的条数")
    vector_top_k: int | None = Field(default=None, ge=1, le=100, description="向量召回候选数")
    bm25_top_k: int | None = Field(default=None, ge=1, le=100, description="BM25 召回候选数")
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0, description="向量相似度阈值")
    use_rerank: bool | None = Field(default=None, description="是否启用 Cross-Encoder 重排")
    rerank_top_n: int | None = Field(default=None, ge=1, le=50, description="重排后保留条数")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, description="用户问题")
    conversation_id: str | None = Field(default=None, description="会话 ID，为空则新建会话")
    retrieval: RetrievalOptions | None = Field(default=None, description="检索参数覆盖")

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value


class SourceItem(BaseModel):
    """引用来源：回答里 [1] 对应的一条检索片段。"""

    index: int
    chunk_id: str
    doc_id: int | None = None
    filename: str
    page: int | None = None
    section: str | None = None
    snippet: str
    vector_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    sources: list[SourceItem] = Field(default_factory=list)
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("标题不能为空")
        return value


class ChatDonePayload(BaseModel):
    """SSE done 事件的负载，方便前端拿到落库后的消息 ID。"""

    message_id: str
    conversation_id: str
    conversation_title: str
    latency_ms: int
