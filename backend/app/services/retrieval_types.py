"""检索结果中间结构。

向量召回、BM25 召回、RRF 融合、重排都围绕它做数据流转，
最终再转换成 LangChain 的 Document 或接口层的 SourceItem。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document

from app.schemas.chat import SourceItem

SNIPPET_MAX_CHARS = 300


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    # 各路召回的原始分，保留下来便于前端展示与后续评估调参
    vector_score: float | None = None
    bm25_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None

    @property
    def filename(self) -> str:
        return str(self.metadata.get("filename") or "未知文档")

    @property
    def page(self) -> int | None:
        value = self.metadata.get("page")
        if value in (None, "", 0):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def section(self) -> str | None:
        value = self.metadata.get("section")
        return str(value) if value else None

    @property
    def doc_id(self) -> int | None:
        value = self.metadata.get("doc_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def location(self) -> str:
        """人类可读来源描述：文件名 第3页 / 章节。"""
        parts = [self.filename]
        if self.page:
            parts.append(f"第 {self.page} 页")
        if self.section:
            parts.append(self.section)
        return " · ".join(parts)

    def to_document(self) -> Document:
        return Document(id=self.chunk_id, page_content=self.text, metadata=dict(self.metadata))

    def to_source(self, index: int) -> SourceItem:
        snippet = self.text.strip()
        if len(snippet) > SNIPPET_MAX_CHARS:
            snippet = snippet[:SNIPPET_MAX_CHARS] + "…"
        return SourceItem(
            index=index,
            chunk_id=self.chunk_id,
            doc_id=self.doc_id,
            filename=self.filename,
            page=self.page,
            section=self.section,
            snippet=snippet,
            vector_score=self.vector_score,
            bm25_score=self.bm25_score,
            rrf_score=round(self.rrf_score, 6) if self.rrf_score else None,
            rerank_score=self.rerank_score,
        )
