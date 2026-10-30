"""RRF 融合与检索模式分发的单元测试。

用假的向量库/BM25 来测融合逻辑，不依赖模型 API，也不需要联网。
"""

from __future__ import annotations

from langchain_core.documents import Document

from app.schemas.chat import RetrievalOptions
from app.services.hybrid_retriever import HybridRetriever
from app.services.reranker import NoopReranker
from app.services.retrieval_types import RetrievedChunk


class _StubVectorStore:
    def __init__(self, hits: list[tuple[str, str, dict, float]]) -> None:
        self.hits = hits

    def search(self, query: str, k: int, score_threshold: float | None = None):
        return [
            (Document(id=chunk_id, page_content=text, metadata=meta), score)
            for chunk_id, text, meta, score in self.hits[:k]
        ]


class _StubBM25Index:
    def __init__(
        self, chunks: dict[str, dict], hits: list[tuple[str, float]]
    ) -> None:
        self._chunks = chunks
        self._hits = hits

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        return self._hits[:k]

    def get_chunk(self, chunk_id: str) -> dict | None:
        return self._chunks.get(chunk_id)


def _chunk(chunk_id: str, text: str) -> dict:
    return {"text": text, "metadata": {"chunk_id": chunk_id, "filename": "a.pdf", "page": 1}}


def _retriever() -> HybridRetriever:
    vector_hits = [
        ("a", "向量排第一", {"chunk_id": "a", "filename": "a.pdf"}, 0.9),
        ("b", "向量排第二", {"chunk_id": "b", "filename": "a.pdf"}, 0.8),
    ]
    bm25_chunks = {
        "b": _chunk("b", "BM25 与向量共同命中"),
        "c": _chunk("c", "只有 BM25 命中"),
    }
    bm25_hits = [("b", 12.5), ("c", 8.0)]
    return HybridRetriever(
        vector_store=_StubVectorStore(vector_hits),
        bm25_index=_StubBM25Index(bm25_chunks, bm25_hits),
        reranker=NoopReranker(),
    )


def test_rrf_prefers_chunks_hit_by_both_routes():
    chunks = _retriever().retrieve("测试查询", RetrievalOptions(mode="hybrid", top_k=3, use_rerank=False))

    assert [chunk.chunk_id for chunk in chunks] == ["b", "a", "c"]
    # 同时命中两路的 b 应该拿到两项 RRF 贡献
    top = chunks[0]
    assert top.vector_score == 0.8
    assert top.bm25_score == 12.5
    assert top.rrf_score > chunks[1].rrf_score


def test_rrf_score_formula():
    retriever = _retriever()
    chunks = retriever.retrieve("测试查询", RetrievalOptions(mode="hybrid", top_k=3, use_rerank=False))
    by_id = {chunk.chunk_id: chunk for chunk in chunks}

    rrf_k = retriever.settings.rrf_k
    # b：向量第 2 名、BM25 第 1 名
    expected_b = 1 / (rrf_k + 2) + 1 / (rrf_k + 1)
    assert abs(by_id["b"].rrf_score - expected_b) < 1e-9


def test_vector_only_mode_keeps_vector_order():
    chunks = _retriever().retrieve("测试查询", RetrievalOptions(mode="vector", top_k=3, use_rerank=False))
    assert [chunk.chunk_id for chunk in chunks] == ["a", "b"]
    assert all(chunk.bm25_score is None for chunk in chunks)


def test_bm25_only_mode_keeps_bm25_order():
    chunks = _retriever().retrieve("测试查询", RetrievalOptions(mode="bm25", top_k=3, use_rerank=False))
    assert [chunk.chunk_id for chunk in chunks] == ["b", "c"]
    assert all(chunk.vector_score is None for chunk in chunks)


def test_final_top_k_truncates():
    chunks = _retriever().retrieve("测试查询", RetrievalOptions(mode="hybrid", top_k=1, use_rerank=False))
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "b"


def test_source_item_carries_page_and_scores():
    chunk = RetrievedChunk(
        chunk_id="x",
        text="一段很长的正文" * 100,
        metadata={"chunk_id": "x", "filename": "手册.pdf", "page": 3, "section": "第二章", "doc_id": 7},
        vector_score=0.75,
        rrf_score=0.032,
    )
    source = chunk.to_source(1)

    assert source.index == 1
    assert source.filename == "手册.pdf"
    assert source.page == 3
    assert source.doc_id == 7
    assert source.snippet.endswith("…")
    assert len(source.snippet) <= 301