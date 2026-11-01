"""向量化服务：调用 DashScope 的 text-embedding-v4 把文本转成向量。

实现 LangChain Embeddings 接口，实例可直接交给 Chroma 使用
要点：分批提交（单次请求的文本条数有上限）+ tenacity 指数退避重试
注意：每次调用都是远程 HTTP 请求，上传大文档时批量成本较高
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.embeddings import Embeddings
from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings, get_settings
from app.core.exceptions import BizException, ErrorCode


class EmbeddingService(Embeddings):
    """实现了 LangChain Embeddings 接口，可直接传给 Chroma。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.embedding_model_name
        self.batch_size = max(1, self.settings.embedding_batch_size)
        self._client = DashScopeEmbeddings(
            model=self.model_name,
            dashscope_api_key=self.settings.dashscope_api_key or None,
        )

    # ---------- LangChain Embeddings 接口 ----------
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch))
            logger.debug(
                "Embedding 批次完成：{}-{}/{}", start, start + len(batch), len(texts)
            )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        result = self._embed_batch([text])
        return result[0]

    # ---------- 内部实现 ----------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=6),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _embed_batch(self, batch: Sequence[str]) -> list[list[float]]:
        try:
            return self._client.embed_documents(list(batch))
        except Exception as exc:
            logger.warning("Embedding 调用失败，准备重试：{}", exc)
            raise

    def embed_query_safe(self, text: str) -> list[float]:
        """查询向量化：失败时转成业务异常，避免把原始堆栈抛给前端。"""
        try:
            return self.embed_query(text)
        except Exception as exc:
            logger.exception("查询向量化失败")
            raise BizException(ErrorCode.EMBEDDING_FAILED, f"向量化失败：{exc}") from exc
