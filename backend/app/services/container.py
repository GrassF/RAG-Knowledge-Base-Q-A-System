"""服务容器：把重量级对象（向量库、BM25 索引、Reranker）在启动时初始化一次。

FastAPI 的 lifespan 负责调用 init_services() / shutdown_services()，
路由通过 get_rag() 拿到同一个实例，避免每个请求重复加载 jieba 词典或重建索引。
"""

from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.services.rag_chain import RagChain

_rag_chain: RagChain | None = None


def init_services() -> None:
    global _rag_chain
    if _rag_chain is not None:
        return
    settings = get_settings()
    logger.info(
        "初始化服务：vector_type={} collection={} retrieval_mode={} rerank={}",
        settings.vector_type,
        settings.collection_name,
        settings.retrieval_mode,
        settings.rerank_model if settings.use_rerank else "disabled",
    )
    _rag_chain = RagChain(settings)
    _rag_chain.ensure_bm25_ready()


def get_rag() -> RagChain:
    if _rag_chain is None:
        # 兜底：脚本或测试里没走 lifespan 时按需初始化
        init_services()
    assert _rag_chain is not None
    return _rag_chain


def shutdown_services() -> None:
    global _rag_chain
    _rag_chain = None
