"""向量库服务（Chroma / PGVector）。

职责边界：只负责向量库的读写，不做切分、不做融合。
检索接口显式暴露 k 与 score_threshold，避免把阈值当 Top-K 用的历史问题。
"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from loguru import logger

from app.core.config import Settings, get_settings
from app.core.exceptions import BizException, ErrorCode
from app.services.splitter import Chunk


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Chroma 只接受 str/int/float/bool，None 会导致写入失败。

    page/section 在 DOCX 里可能为空，这里直接丢掉空值，
    读取时用 metadata.get(...) 取不到自然会变成 None。
    """
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


class VectorStoreService:
    def __init__(self, embedding, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.embedding = embedding
        self._store = self._build_store()

    def _build_store(self):
        settings = self.settings
        if settings.vector_type == "chroma":
            from langchain_chroma import Chroma

            settings.chroma_path.mkdir(parents=True, exist_ok=True)
            return Chroma(
                collection_name=settings.collection_name,
                embedding_function=self.embedding,
                persist_directory=str(settings.chroma_path),
                # 显式指定余弦距离，否则 Chroma 默认是 L2
                collection_metadata={"hnsw:space": "cosine"},
            )

        if settings.vector_type == "pgvector":
            # 懒加载：只用 chroma 时不必安装 pgvector 相关依赖
            from langchain_community.vectorstores import PGVector

            return PGVector(
                collection_name=settings.pg_collection_name,
                embedding_function=self.embedding,
                connection_string=settings.pg_connection_string,
            )

        raise BizException(ErrorCode.INTERNAL_ERROR, f"未知的向量库类型：{settings.vector_type}")

    # ===================== 写入 =====================
    def add_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        try:
            self._store.add_texts(
                texts=[chunk.text for chunk in chunks],
                metadatas=[_sanitize_metadata(chunk.metadata) for chunk in chunks],
                ids=[chunk.chunk_id for chunk in chunks],
            )
        except Exception as exc:
            logger.exception("写入向量库失败")
            raise BizException(ErrorCode.INDEX_ERROR, f"写入向量库失败：{exc}") from exc
        return len(chunks)

    # ===================== 检索 =====================
    def search(
        self, query: str, k: int, score_threshold: float | None = None
    ) -> list[tuple[Document, float]]:
        """返回 (文档, 相似度) 列表，相似度为 cosine relevance（越大越相关）。"""
        total = self.count()
        if total == 0:
            return []

        limit = max(1, min(k, total))
        try:
            pairs = self._store.similarity_search_with_relevance_scores(query, k=limit)
        except Exception as exc:
            logger.exception("向量检索失败")
            raise BizException(ErrorCode.INDEX_ERROR, f"向量检索失败：{exc}") from exc

        threshold = score_threshold or 0.0
        if threshold > 0:
            pairs = [(doc, score) for doc, score in pairs if score >= threshold]
        return pairs

    # ===================== 读取 / 删除 =====================
    def count(self) -> int:
        try:
            collection = getattr(self._store, "_collection", None)
            if collection is not None:
                return int(collection.count())
            return len(self._store.get(include=[])["ids"])
        except Exception:
            return 0

    def list_by_doc_id(self, doc_id: int) -> list[Document]:
        try:
            data = self._store.get(where={"doc_id": int(doc_id)})
        except Exception as exc:
            logger.warning("按 doc_id 查询向量库失败：{}", exc)
            return []
        return [
            Document(id=doc_id_str, page_content=text, metadata=meta or {})
            for doc_id_str, text, meta in zip(
                data.get("ids") or [], data.get("documents") or [], data.get("metadatas") or []
            )
        ]

    def all_documents(self) -> list[Document]:
        """全量导出，BM25 索引重建时使用。"""
        try:
            data = self._store.get(include=["documents", "metadatas"])
        except Exception as exc:
            logger.warning("导出向量库数据失败：{}", exc)
            return []
        return [
            Document(id=doc_id_str, page_content=text, metadata=meta or {})
            for doc_id_str, text, meta in zip(
                data.get("ids") or [], data.get("documents") or [], data.get("metadatas") or []
            )
        ]

    def delete_by_doc_id(self, doc_id: int) -> int:
        before = len(self.list_by_doc_id(doc_id))
        if before:
            try:
                self._store.delete(where={"doc_id": int(doc_id)})
            except Exception as exc:
                logger.exception("删除向量失败")
                raise BizException(ErrorCode.INDEX_ERROR, f"删除向量失败：{exc}") from exc
        return before

    def delete_by_doc_ids(self, doc_ids: list[int]) -> int:
        deleted = 0
        for doc_id in doc_ids:
            deleted += self.delete_by_doc_id(doc_id)
        return deleted

    def drop(self) -> int:
        """清空整个集合，返回清空前的向量数量。"""
        total = self.count()
        try:
            self._store.delete_collection()
        except Exception as exc:
            logger.exception("清空向量库失败")
            raise BizException(ErrorCode.INDEX_ERROR, f"清空向量库失败：{exc}") from exc
        # 删完立刻重建空集合，保证后续读写正常
        self._store = self._build_store()
        return total
