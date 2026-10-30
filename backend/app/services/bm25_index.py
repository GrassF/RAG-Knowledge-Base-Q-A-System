"""BM25 关键词索引。

为什么需要它：向量检索擅长语义相似，但对"精确术语 / 型号 / 编号 / 人名"这类
字面匹配经常翻车，BM25 正好补上这块短板，两者用 RRF 融合。

实现要点：
- 中文用 jieba 的搜索引擎模式分词，与向量侧共用同一份 chunk 文本
- 索引以 chunk_id 为键常驻内存，文档增删后重建（千级切片耗时毫秒级）
- 持久化到 pkl，进程重启不必重新分词
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

import jieba
from langchain_core.documents import Document
from loguru import logger
from rank_bm25 import BM25Okapi

from app.services.splitter import Chunk

jieba.setLogLevel(logging.WARNING)

_WORD_CHAR = re.compile(r"\w")

# 精简停用词表：只保留对检索有明显干扰的高频虚词
STOPWORDS = {
    "的", "了", "和", "是", "在", "有", "与", "及", "或", "也", "就", "都", "而",
    "对", "把", "被", "这", "那", "我", "你", "他", "她", "它", "我们", "你们",
    "这个", "那个", "一个", "什么", "怎么", "如何", "为什么", "请问", "可以",
    "the", "a", "an", "of", "to", "and", "or", "is", "are", "in", "on", "for",
}


class BM25Index:
    def __init__(self, path: Path, k1: float = 1.5, b: float = 0.75) -> None:
        self._path = Path(path)
        self._k1 = k1
        self._b = b
        # chunk_id -> {"tokens": [...], "text": str, "metadata": dict}
        self._docs: dict[str, dict[str, Any]] = {}
        self._ordered_ids: list[str] = []
        self._bm25: BM25Okapi | None = None
        self._lock = threading.RLock()

    # ===================== 分词 =====================
    @staticmethod
    def tokenize(text: str) -> list[str]:
        tokens: list[str] = []
        for raw in jieba.lcut_for_search(text.lower()):
            token = raw.strip()
            if not token or token in STOPWORDS:
                continue
            # 纯标点、纯空白直接丢弃
            if not _WORD_CHAR.search(token):
                continue
            tokens.append(token)
        return tokens

    @staticmethod
    def warm_up() -> None:
        """启动时预热词典，避免第一个请求卡顿。"""
        jieba.initialize()

    # ===================== 写入 =====================
    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        with self._lock:
            for chunk in chunks:
                self._docs[chunk.chunk_id] = {
                    "tokens": self.tokenize(chunk.text),
                    "text": chunk.text,
                    "metadata": {k: v for k, v in chunk.metadata.items() if v is not None},
                }
            self._rebuild()
            self._save()
        logger.info("BM25 索引已更新，当前切片数：{}", len(self._docs))

    def remove_by_doc_id(self, doc_id: int) -> int:
        with self._lock:
            targets = [
                chunk_id
                for chunk_id, item in self._docs.items()
                if str(item["metadata"].get("doc_id")) == str(doc_id)
            ]
            for chunk_id in targets:
                self._docs.pop(chunk_id, None)
            if targets:
                self._rebuild()
                self._save()
        return len(targets)

    def rebuild_from_documents(self, documents: list[Document]) -> int:
        """从向量库全量重建（启动时索引文件缺失的兜底方案）。"""
        with self._lock:
            self._docs.clear()
            for document in documents:
                chunk_id = str(document.metadata.get("chunk_id") or document.id or "")
                if not chunk_id:
                    continue
                self._docs[chunk_id] = {
                    "tokens": self.tokenize(document.page_content),
                    "text": document.page_content,
                    "metadata": {
                        k: v for k, v in (document.metadata or {}).items() if v is not None
                    },
                }
            self._rebuild()
            self._save()
        logger.info("BM25 索引已从向量库重建，共 {} 个切片", len(self._docs))
        return len(self._docs)

    def clear(self) -> None:
        with self._lock:
            self._docs.clear()
            self._ordered_ids = []
            self._bm25 = None
            self._save()

    # ===================== 检索 =====================
    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        """返回 [(chunk_id, bm25_score)]，按分数降序。"""
        with self._lock:
            if self._bm25 is None or not self._ordered_ids:
                return []
            tokens = self.tokenize(query)
            if not tokens:
                return []
            scores = self._bm25.get_scores(tokens)
            ranked = sorted(
                zip(self._ordered_ids, scores), key=lambda item: item[1], reverse=True
            )

        # BM25Okapi 对高频词可能给出负分，负分结果没有检索意义
        return [(chunk_id, float(score)) for chunk_id, score in ranked[:k] if score > 0]

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._docs.get(chunk_id)
            return dict(item) if item else None

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._docs)

    # ===================== 持久化 =====================
    def load(self) -> bool:
        """加载持久化索引，成功返回 True。"""
        if not self._path.exists():
            return False
        try:
            with self._path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception as exc:  # 文件损坏时退化为重建
            logger.warning("BM25 索引文件读取失败，将重建：{}", exc)
            return False

        if not isinstance(payload, dict):
            return False

        with self._lock:
            self._docs = payload
            self._rebuild()
        logger.info("BM25 索引已加载：{} 个切片", len(self._docs))
        return True

    def _save(self) -> None:
        """JSON 落盘：可读、无 pickle 反序列化风险。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(self._docs, file, ensure_ascii=False)
            tmp_path.replace(self._path)
        except Exception as exc:  # 落盘失败不应影响主流程
            logger.warning("BM25 索引持久化失败：{}", exc)

    def _rebuild(self) -> None:
        self._ordered_ids = list(self._docs.keys())
        if not self._ordered_ids:
            self._bm25 = None
            return
        corpus = [self._docs[chunk_id]["tokens"] for chunk_id in self._ordered_ids]
        self._bm25 = BM25Okapi(corpus, k1=self._k1, b=self._b)
