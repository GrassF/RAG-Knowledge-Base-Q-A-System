"""Cross-Encoder 重排序。

初步召回（向量 + BM25 融合）拿到的是"可能相关"的候选，顺序并不精确；
Reranker 把 query 与每个候选拼在一起做一次相关性打分，按分数重排，
这是提升 RAG 回答准确率最有效的一步。

模型选择：
- gte-rerank-v2  走 DashScope 标准端点  /api/v1/services/rerank/text-rerank/text-rerank
- qwen3-rerank   走 OpenAI 兼容端点     /compatible-api/v1/reranks
两者报文结构不同，所以分成两个实现，由工厂按配置选择。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import requests
from loguru import logger

from app.core.config import Settings, get_settings
from app.services.retrieval_types import RetrievedChunk

# 单条候选参与重排的最大字符数，避免长切片把请求 token 打满
_MAX_DOC_CHARS = 2000
# 单次请求最多提交的候选数
_MAX_DOCUMENTS = 50


class BaseReranker(ABC):
    name: str = "base"

    @abstractmethod
    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        """返回按相关性重排后的切片，score 写入 chunk.rerank_score。"""


class NoopReranker(BaseReranker):
    """关闭重排时的直通实现。"""

    name = "noop"

    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        return chunks[:top_n]


class _HttpReranker(BaseReranker):
    """两个 HTTP 实现的公共部分：请求、解析、失败降级。"""

    def __init__(self, settings: Settings, model: str, url: str, timeout: float) -> None:
        self.settings = settings
        self.model = model
        self.url = url
        self.timeout = timeout

    def build_payload(self, query: str, documents: list[str], top_n: int) -> dict[str, Any]:
        raise NotImplementedError

    def extract_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        if len(chunks) == 1:
            # 只有一个候选，重排没有意义，直接返回省一次 API 调用
            return chunks[:top_n]

        candidates = chunks[:_MAX_DOCUMENTS]
        documents = [chunk.text[:_MAX_DOC_CHARS] for chunk in candidates]
        try:
            results = self._call(query, documents, min(top_n, len(documents)))
        except Exception as exc:
            # 重排是"增强"而不是"必需"，失败必须降级，不能把问答打断
            logger.warning("{} 重排失败，已降级为融合排序：{}", self.name, exc)
            return chunks[:top_n]

        if not results:
            logger.warning("{} 返回空结果，已降级为融合排序", self.name)
            return chunks[:top_n]

        ordered: list[RetrievedChunk] = []
        used: set[int] = set()
        for item in results:
            index = item.get("index")
            if index is None or not isinstance(index, int) or not 0 <= index < len(candidates):
                continue
            if index in used:
                continue
            used.add(index)
            chunk = candidates[index]
            score = item.get("relevance_score")
            chunk.rerank_score = float(score) if score is not None else None
            ordered.append(chunk)

        if not ordered:
            return chunks[:top_n]
        return ordered[:top_n]

    def _call(self, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }
        payload = self.build_payload(query, documents, top_n)
        response = requests.post(self.url, json=payload, headers=headers, timeout=self.timeout)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        return self.extract_results(response.json())


class DashScopeReranker(_HttpReranker):
    """DashScope 标准文本排序接口（gte-rerank-v2）。"""

    name = "dashscope"

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings=settings,
            model=settings.rerank_model,
            url=f"{settings.dashscope_base_url.rstrip('/')}/services/rerank/text-rerank/text-rerank",
            timeout=settings.rerank_timeout,
        )

    def build_payload(self, query: str, documents: list[str], top_n: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": False, "top_n": top_n},
        }

    def extract_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        output = payload.get("output") or {}
        return list(output.get("results") or [])


class QwenReranker(_HttpReranker):
    """qwen3-rerank 走 OpenAI 兼容端点，请求体是扁平的。"""

    name = "qwen3"

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings=settings,
            model=settings.rerank_model,
            url=f"{settings.dashscope_compatible_base_url.rstrip('/')}/reranks",
            timeout=settings.rerank_timeout,
        )

    def build_payload(self, query: str, documents: list[str], top_n: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "instruct": "Given a web search query, retrieve relevant passages that answer the query.",
        }

    def extract_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("results")
        if results is None:
            results = (payload.get("output") or {}).get("results") or []
        return list(results or [])


def create_reranker(settings: Settings | None = None) -> BaseReranker:
    """按配置创建重排器。"""
    settings = settings or get_settings()
    if not settings.use_rerank:
        return NoopReranker()

    model = settings.rerank_model.strip().lower()
    if model.startswith("qwen3"):
        logger.info("重排器：qwen3-rerank（OpenAI 兼容端点）")
        return QwenReranker(settings)

    logger.info("重排器：{}（DashScope 标准端点）", settings.rerank_model)
    return DashScopeReranker(settings)
