"""文档解析的统一中间格式。

解析层只负责"把文件变成本地的结构化文本块"，不做清洗和切分。
保留 page / section 是为了让最终的回答能追溯到"哪个文件第几页哪一节"。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# 章节标题的常见写法：第2章、2.1 概述、一、总则、## 标题
_HEADING_PATTERNS = (
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+[章节篇部分]\s*"),
    re.compile(r"^\d+(\.\d+){0,3}[\s、.]+[\u4e00-\u9fa5A-Za-z]"),
    re.compile(r"^[一二三四五六七八九十]+[、.]\s*"),
    re.compile(r"^#{1,6}\s+\S"),
    re.compile(r"^(附录|附錄|前言|目录|目錄|摘要|参考文献)\s*"),
)


@dataclass
class ParsedBlock:
    """解析出的一个文本块。"""

    text: str
    page: int | None = None
    section: str | None = None
    # paragraph / table / heading
    kind: str = "paragraph"


@dataclass
class ParseResult:
    blocks: list[ParsedBlock] = field(default_factory=list)
    page_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not any(block.text.strip() for block in self.blocks)

    @property
    def section_count(self) -> int:
        return len({block.section for block in self.blocks if block.section})

    def iter_text(self) -> list[str]:
        return [block.text for block in self.blocks]


class BaseParser(ABC):
    """解析器接口。新增格式只需实现 parse 并注册到 registry。"""

    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, data: bytes) -> ParseResult:
        """把文件二进制解析成结构化文本块。"""


def detect_heading(line: str) -> str | None:
    """判断一行是否是标题，返回标题文本（未命中返回 None）。

    仅做启发式判断，宁可漏判也不要误判：正文里出现 "1. " 这种列表也算标题，
    对切分影响不大（只是多一个 section 边界）。
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return None
    for pattern in _HEADING_PATTERNS:
        if pattern.match(stripped):
            return stripped.lstrip("#").strip()
    return None


def push_section(stack: list[tuple[int, str]], heading: str) -> str:
    """把标题压入层级栈，返回 "第2章 > 2.1 概述" 形式的路径。

    用编号深度（第N章=1，2.1=2，2.1.1=3）决定层级，避免标题栈无限增长。
    """
    depth = _heading_depth(heading)
    while stack and stack[-1][0] >= depth:
        stack.pop()
    stack.append((depth, heading))
    return " > ".join(text for _, text in stack[-3:])


def _heading_depth(heading: str) -> int:
    if re.match(r"^第[一二三四五六七八九十百零〇\d]+[章节篇部分]", heading):
        return 1
    numbered = re.match(r"^(\d+(?:\.\d+)*)", heading)
    if numbered:
        return numbered.group(1).count(".") + 1
    if re.match(r"^[一二三四五六七八九十]+[、.]", heading):
        return 1
    if heading.startswith("#"):
        return len(heading) - len(heading.lstrip("#"))
    return 2
