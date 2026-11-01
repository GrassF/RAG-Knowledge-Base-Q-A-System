"""混合检索总控：向量召回 ∥ BM25 召回 → RRF 融合 → Cross-Encoder 重排。

参数来源：请求里的 RetrievalOptions 逐项覆盖 .env 默认值（resolve_options）
要点：两路召回用线程池并行执行；RRF 只依据排名、不依据原始分数，
      从而规避「余弦相似度」与「BM25 分值」量纲不同无法相加的问题
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from loguru import logger

from app.core.config import Settings, get_settings
from app.schemas.chat import RetrievalOptions
from app.services.bm25_index import BM25Index
from app.services.cleaning import normalize_query
from app.services.reranker import BaseReranker, create_reranker
from app.services.retrieval_types import RetrievedChunk
from app.services.vector_store import VectorStoreService


@dataclass
class ResolvedRetrievalConfig:
    mode: str
    vector_top_k: int
    bm25_top_k: int
    final_top_k: int
    score_threshold: float
    use_rerank: bool
    rerank_top_n: int
    rrf_k: int


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStoreService,
        bm25_index: BM25Index,
        reranker: BaseReranker | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.reranker = reranker or create_reranker(self.settings)

    # ===================== 参数解析 =====================
    def resolve_options(self, options: RetrievalOptions | None) -> ResolvedRetrievalConfig:
        settings = self.settings
        options = options or RetrievalOptions()

        return ResolvedRetrievalConfig(
            mode=options.mode or settings.retrieval_mode,
            vector_top_k=options.vector_top_k or settings.vector_top_k,
            bm25_top_k=options.bm25_top_k or settings.bm25_top_k,
            final_top_k=options.top_k or settings.final_top_k,
            score_threshold=(
                options.score_threshold
                if options.score_threshold is not None
                else settings.score_threshold
            ),
            use_rerank=options.use_rerank if options.use_rerank is not None else settings.use_rerank,
            rerank_top_n=options.rerank_top_n or settings.rerank_top_n,
            rrf_k=settings.rrf_k,
        )

    # ===================== 主流程 =====================
    def retrieve(
        self, query: str, options: RetrievalOptions | None = None
    ) -> list[RetrievedChunk]:
        config = self.resolve_options(options)
        query = normalize_query(query)
        if not query:
            return []

        vector_hits: list[tuple[str, str, dict, float]] = []
        bm25_hits: list[tuple[str, float]] = []

        if config.mode in ("vector", "hybrid"):
            if config.mode == "hybrid":
                # 两路召回互不依赖，并行执行
                with ThreadPoolExecutor(max_workers=2, thread_name_prefix="recall") as executor:
                    vector_future = executor.submit(
                        self._vector_recall, query, config.vector_top_k, config.score_threshold
                    )
                    bm25_future = executor.submit(self._bm25_recall, query, config.bm25_top_k)
                    vector_hits = vector_future.result()
                    bm25_hits = bm25_future.result()
            else:
                vector_hits = self._vector_recall(query, config.vector_top_k, config.score_threshold)
        else:
            bm25_hits = self._bm25_recall(query, config.bm25_top_k)

        fused = self._fuse(vector_hits, bm25_hits, config.rrf_k)
        logger.info(
            "召回完成：mode={} vector={} bm25={} fused={}",
            config.mode,
            len(vector_hits),
            len(bm25_hits),
            len(fused),
        )

        if not fused:
            return []

        # 重排：取融合后的前 rerank_top_n 条送进 Cross-Encoder
        candidates = fused[: max(config.rerank_top_n, config.final_top_k)]
        if config.use_rerank:
            reranked = self.reranker.rerank(query, candidates, config.final_top_k)
            if reranked:
                candidates = reranked

        return candidates[: config.final_top_k]

    # ===================== 各路召回 =====================
    def _vector_recall(
        self, query: str, k: int, score_threshold: float
    ) -> list[tuple[str, str, dict, float]]:
        pairs = self.vector_store.search(query, k=k, score_threshold=score_threshold)
        hits: list[tuple[str, str, dict, float]] = []
        for document, score in pairs:
            chunk_id = str(document.metadata.get("chunk_id") or document.id or "")
            if not chunk_id:
                continue
            hits.append((chunk_id, document.page_content, dict(document.metadata or {}), float(score)))
        return hits

    def _bm25_recall(self, query: str, k: int) -> list[tuple[str, float]]:
        raw_hits = self.bm25_index.search(query, k=k)
        valid: list[tuple[str, float]] = []
        for chunk_id, score in raw_hits:
            if self.bm25_index.get_chunk(chunk_id) is None:
                continue
            valid.append((chunk_id, score))
        return valid

    # ===================== RRF 融合 =====================
    def _fuse(
        self,
        vector_hits: list[tuple[str, str, dict, float]],
        bm25_hits: list[tuple[str, float]],
        rrf_k: int,
    ) -> list[RetrievedChunk]:
        merged: dict[str, RetrievedChunk] = {}

        for rank, (chunk_id, text, metadata, score) in enumerate(vector_hits, start=1):
            chunk = merged.get(chunk_id) or RetrievedChunk(chunk_id=chunk_id, text=text, metadata=metadata)
            chunk.vector_score = score
            chunk.rrf_score += 1.0 / (rrf_k + rank)
            merged[chunk_id] = chunk

        for rank, (chunk_id, score) in enumerate(bm25_hits, start=1):
            chunk = merged.get(chunk_id)
            if chunk is None:
                # 只在 BM25 命中里出现的切片，从索引里补齐正文与元数据
                item = self.bm25_index.get_chunk(chunk_id)
                if item is None:
                    continue
                chunk = RetrievedChunk(
                    chunk_id=chunk_id,
                    text=str(item.get("text") or ""),
                    metadata=dict(item.get("metadata") or {}),
                )
                merged[chunk_id] = chunk
            chunk.bm25_score = score
            chunk.rrf_score += 1.0 / (rrf_k + rank)

        return sorted(merged.values(), key=lambda item: item.rrf_score, reverse=True)
