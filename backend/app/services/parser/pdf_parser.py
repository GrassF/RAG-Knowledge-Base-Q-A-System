"""PDF 解析：逐页提取文本，保留页码，并剔除页眉页脚。

关键点：
1. 必须逐页处理，否则拿不到页码，回答就无法追溯来源。
2. 页眉页脚/页码会污染检索结果（每页都有，与问题无关却频繁命中），
   这里用"跨页重复率"启发式自动识别。
"""

from __future__ import annotations

import re
from collections import Counter
from io import BytesIO

from loguru import logger
from pypdf import PdfReader

from app.core.exceptions import BizException, ErrorCode
from app.services.parser.base import BaseParser, ParsedBlock, ParseResult, detect_heading, push_section

# 纯页码行：3 / - 3 - / 第 3 页 / Page 3 of 10
_PAGE_NUMBER_PATTERN = re.compile(
    r"^[-—\s]*(第\s*\d+\s*页|page\s*\d+(\s*of\s*\d+)?|\d{1,4})[-—\s]*$", re.IGNORECASE
)
_DIGITS = re.compile(r"\d+")

HEADER_FOOTER_RATIO = 0.6
MIN_PAGES_FOR_DETECTION = 3


class PdfParser(BaseParser):
    extensions = (".pdf",)

    def parse(self, data: bytes) -> ParseResult:
        try:
            reader = PdfReader(BytesIO(data))
        except Exception as exc:  # 加密、损坏的文件
            raise BizException(ErrorCode.DOC_PARSE_FAILED, f"PDF 文件无法打开：{exc}") from exc

        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:
                raise BizException(ErrorCode.DOC_PARSE_FAILED, "PDF 已加密，无法解析") from exc

        pages_lines: list[list[str]] = []
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # 单页失败不影响整体
                logger.warning("PDF 单页解析失败，已跳过：{}", exc)
                text = ""
            pages_lines.append([line.rstrip() for line in text.splitlines()])

        drop_lines = self._detect_header_footer(pages_lines)

        blocks: list[ParsedBlock] = []
        for page_index, lines in enumerate(pages_lines, start=1):
            blocks.extend(self._build_page_blocks(page_index, lines, drop_lines))

        logger.info(
            "PDF 解析完成：{} 页，剔除页眉页脚 {} 条，生成 {} 个文本块",
            len(pages_lines),
            len(drop_lines),
            len(blocks),
        )
        return ParseResult(blocks=blocks, page_count=len(pages_lines))

    @staticmethod
    def _normalize_for_match(line: str) -> str:
        """把数字统一成 #，让 "第 3 页" 和 "第 4 页" 能被识别为同一条页眉。"""
        return _DIGITS.sub("#", line.strip())

    def _detect_header_footer(self, pages_lines: list[list[str]]) -> set[str]:
        """统计每页首行/末行的跨页重复率，重复率高的视为页眉页脚。"""
        if len(pages_lines) < MIN_PAGES_FOR_DETECTION:
            return set()

        counter: Counter[str] = Counter()
        edge_total = 0
        for lines in pages_lines:
            non_empty = [line.strip() for line in lines if line.strip()]
            if not non_empty:
                continue
            edge_total += 1
            for candidate in {self._normalize_for_match(non_empty[0]), self._normalize_for_match(non_empty[-1])}:
                counter[candidate] += 1

        threshold = max(MIN_PAGES_FOR_DETECTION, int(edge_total * HEADER_FOOTER_RATIO))
        return {line for line, count in counter.items() if count >= threshold}

    def _build_page_blocks(
        self, page_index: int, lines: list[str], drop_lines: set[str]
    ) -> list[ParsedBlock]:
        """按标题把一页拆成若干块，同时维护章节路径。"""
        blocks: list[ParsedBlock] = []
        buffer: list[str] = []
        section_stack: list[tuple[int, str]] = []
        current_section: str | None = None

        def flush() -> None:
            nonlocal buffer
            text = "\n".join(buffer).strip()
            if text:
                blocks.append(ParsedBlock(text=text, page=page_index, section=current_section))
            buffer = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                # 空行保留为段落分隔，但不让连续空行堆积
                if buffer and buffer[-1] != "":
                    buffer.append("")
                continue
            if self._normalize_for_match(line) in drop_lines or _PAGE_NUMBER_PATTERN.match(line):
                continue

            heading = detect_heading(line)
            if heading:
                flush()
                current_section = push_section(section_stack, heading)
                blocks.append(
                    ParsedBlock(text=heading, page=page_index, section=current_section, kind="heading")
                )
                continue

            buffer.append(line)

        flush()
        return blocks
