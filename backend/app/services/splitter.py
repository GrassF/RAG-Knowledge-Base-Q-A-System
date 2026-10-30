"""结构感知切分。

与"把全文拼成一个大字符串再切"相比，这里先在解析层拿到的 block（页 / 章节边界）
内部切分，再合并同页同章节的过短片段，做到：
- 切片不跨页、不跨章节，页码与章节归属准确
- 中文按句号/问号等真实语句边界断开，不切半句话
- 每片都带 char_start / char_end，可回查原文位置
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from app.core.config import get_settings
from app.services.cleaning import clean_text, has_content, is_meaningful_chunk
from app.services.parser.base import ParsedBlock

# 中文优先的分隔符：段落 -> 换行 -> 句末标点 -> 分句 -> 空格 -> 按字符兜底
DEFAULT_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    ". ",
    "! ",
    "? ",
    "; ",
    "，",
    " ",
    "",
]


@dataclass
class Chunk:
    """一个待入库的切片。"""

    chunk_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentSplitter:
    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        min_chunk_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
        self.min_chunk_size = min_chunk_size or settings.min_chunk_size
        self.embedding_model = settings.embedding_model_name

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=DEFAULT_SEPARATORS,
            length_function=len,
            keep_separator="end",
            add_start_index=True,
        )

    def split(self, blocks: list[ParsedBlock], base_metadata: dict[str, Any]) -> list[Chunk]:
        """把解析块切成最终入库的切片列表。"""
        raw_chunks: list[dict[str, Any]] = []
        offset = 0  # 块在"整篇文档"中的字符偏移，用于计算全局 char_start

        for block in blocks:
            text = clean_text(block.text)
            if not text:
                offset += 1
                continue
            if not has_content(text):
                offset += len(text) + 1
                continue

            for document in self._splitter.create_documents([text], metadatas=[{}]):
                start = int(document.metadata.get("start_index", 0))
                raw_chunks.append(
                    {
                        "text": document.page_content,
                        "char_start": offset + start,
                        "char_end": offset + start + len(document.page_content),
                        "page": block.page,
                        "section": block.section,
                        "kind": block.kind,
                    }
                )
            offset += len(text) + 1

        merged = self._merge_short_chunks(raw_chunks)
        chunks = self._finalize(merged, base_metadata)
        logger.info(
            "切分完成：{} 个解析块 -> {} 个切片（chunk_size={}, overlap={}）",
            len(blocks),
            len(chunks),
            self.chunk_size,
            self.chunk_overlap,
        )
        return chunks

    def _merge_short_chunks(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """同页同章节的过短片段向后合并，避免"只有标题"这种无效切片。"""
        merged: list[dict[str, Any]] = []
        for item in raw:
            if (
                merged
                and len(merged[-1]["text"]) < self.min_chunk_size
                and merged[-1]["page"] == item["page"]
                and merged[-1]["section"] == item["section"]
                and len(merged[-1]["text"]) + len(item["text"]) + 1 <= self.chunk_size
            ):
                previous = merged[-1]
                previous["text"] = f"{previous['text']}\n{item['text']}".strip()
                previous["char_end"] = item["char_end"]
                continue
            merged.append(dict(item))
        return merged

    def _finalize(
        self, raw: list[dict[str, Any]], base_metadata: dict[str, Any]
    ) -> list[Chunk]:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chunks: list[Chunk] = []
        for index, item in enumerate(raw):
            text = item["text"].strip()
            if not is_meaningful_chunk(text, 10):
                continue
            chunk_id = uuid.uuid4().hex
            metadata = {
                **base_metadata,
                "chunk_id": chunk_id,
                "chunk_index": len(chunks),
                "page": item["page"],
                "section": item["section"],
                "kind": item["kind"],
                "char_start": item["char_start"],
                "char_end": item["char_end"],
                "source_index": index,
                "create_time": created_at,
                "embedding_model": self.embedding_model,
            }
            chunks.append(Chunk(chunk_id=chunk_id, text=text, metadata=metadata))
        return chunks
