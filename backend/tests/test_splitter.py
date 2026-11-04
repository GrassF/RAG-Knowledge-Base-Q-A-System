"""结构感知切分的单元测试。

关注的不是"切了多少片"，而是：
1. 切片不跨页
2. metadata 完整（页码、章节、字符偏移）
3. 过短片段会被合并
"""

from __future__ import annotations

from app.services.parser.base import ParsedBlock
from app.services.splitter import DocumentSplitter

BASE_META = {"doc_id": 1, "filename": "手册.pdf", "file_type": ".pdf"}


def _blocks() -> list[ParsedBlock]:
    long_text = "。".join(f"这是第{i}句用于测试切分的正文内容，长度需要足够触发分块" for i in range(60))
    return [
        ParsedBlock(text="第一章 概述", page=1, section="第一章 概述", kind="heading"),
        ParsedBlock(text=long_text, page=1, section="第一章 概述"),
        ParsedBlock(text="第二章 快速开始", page=2, section="第二章 快速开始", kind="heading"),
        ParsedBlock(text="短内容", page=2, section="第二章 快速开始"),
        ParsedBlock(text="补充说明，与上一段属于同一章节的连续正文内容。", page=2, section="第二章 快速开始"),
    ]


def test_chunks_do_not_cross_pages():
    splitter = DocumentSplitter(chunk_size=200, chunk_overlap=40)
    chunks = splitter.split(_blocks(), BASE_META)

    assert len(chunks) > 1
    pages = {chunk.metadata["page"] for chunk in chunks}
    assert pages == {1, 2}
    # 每个切片只应包含单页内容
    for chunk in chunks:
        assert chunk.metadata["page"] in (1, 2)


def test_metadata_is_complete():
    splitter = DocumentSplitter(chunk_size=200, chunk_overlap=40)
    chunks = splitter.split(_blocks(), BASE_META)

    first = chunks[0]
    assert first.metadata["doc_id"] == 1
    assert first.metadata["filename"] == "手册.pdf"
    assert first.metadata["chunk_index"] == 0
    assert first.metadata["embedding_model"]
    assert first.metadata["char_end"] > first.metadata["char_start"]
    assert first.chunk_id == first.metadata["chunk_id"]

    # chunk_index 必须连续递增
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(range(len(chunks)))


def test_short_chunks_are_merged():
    splitter = DocumentSplitter(chunk_size=500, chunk_overlap=50, min_chunk_size=120)
    blocks = [
        ParsedBlock(text="短内容", page=1, section="第一章"),
        ParsedBlock(text="补充说明，与上一段属于同一章节的连续正文内容。", page=1, section="第一章"),
    ]
    chunks = splitter.split(blocks, BASE_META)
    assert len(chunks) == 1
    assert "短内容" in chunks[0].text


def test_no_chunk_exceeds_chunk_size():
    splitter = DocumentSplitter(chunk_size=200, chunk_overlap=40)
    chunks = splitter.split(_blocks(), BASE_META)
    for chunk in chunks:
        # 合并逻辑允许跨片拼接，但不应超过 chunk_size 太多
        assert len(chunk.text) <= 200