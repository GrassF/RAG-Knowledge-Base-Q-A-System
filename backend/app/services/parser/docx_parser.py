"""DOCX 解析：按文档流顺序抽取段落与表格，并按标题层级生成章节路径。

python-docx 的 doc.paragraphs 会丢掉表格和顺序信息，所以这里直接遍历
document.element.body 的子元素，保证段落与表格的相对顺序与原文一致。
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from loguru import logger

from app.core.exceptions import BizException, ErrorCode
from app.services.parser.base import BaseParser, ParsedBlock, ParseResult, detect_heading, push_section

# Word 内置样式名：Heading 1 / 标题 1
_HEADING_STYLE = re.compile(r"^(heading|标题)\s*(\d)$", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class DocxParser(BaseParser):
    extensions = (".docx",)

    def parse(self, data: bytes) -> ParseResult:
        try:
            document = DocxDocument(BytesIO(data))
        except Exception as exc:
            raise BizException(ErrorCode.DOC_PARSE_FAILED, f"DOCX 文件无法打开：{exc}") from exc

        blocks: list[ParsedBlock] = []
        buffer: list[str] = []
        section_stack: list[tuple[int, str]] = []
        current_section: str | None = None

        def flush() -> None:
            nonlocal buffer
            text = "\n".join(buffer).strip()
            if text:
                blocks.append(ParsedBlock(text=text, page=None, section=current_section))
            buffer = []

        body = document.element.body
        for child in body.iterchildren():
            if child.tag == qn("w:p"):
                paragraph = Paragraph(child, document)
                raw_text = self._clean_cell(paragraph.text)
                if not raw_text:
                    continue
                heading = self._heading_from_style(paragraph) or detect_heading(raw_text)
                if heading:
                    flush()
                    current_section = push_section(section_stack, heading)
                    blocks.append(
                        ParsedBlock(text=heading, page=None, section=current_section, kind="heading")
                    )
                    continue
                buffer.append(raw_text)
            elif child.tag == qn("w:tbl"):
                table = Table(child, document)
                markdown = self._table_to_markdown(table)
                if markdown:
                    flush()
                    blocks.append(
                        ParsedBlock(
                            text=markdown, page=None, section=current_section, kind="table"
                        )
                    )

        flush()

        # docx 没有稳定页码，用"第几个块"兜底，便于前端展示定位
        logger.info("DOCX 解析完成：{} 个文本块，{} 个章节", len(blocks), len(section_stack))
        return ParseResult(blocks=blocks, page_count=0)

    @staticmethod
    def _heading_from_style(paragraph: Paragraph) -> str | None:
        """优先用 Word 的大纲级别判断标题，比正则更可靠。"""
        try:
            style_name = paragraph.style.name if paragraph.style is not None else ""
            outline_level = paragraph.paragraph_format.outline_level
        except Exception:
            return None

        text = paragraph.text.strip()
        if not text:
            return None

        matched = _HEADING_STYLE.match(style_name or "")
        if matched:
            # 把 "Heading 1" 转成 "1"，让 push_section 能算出层级
            return f"{matched.group(2)} {text}"

        if outline_level is not None and int(outline_level) < 9:
            return f"{int(outline_level) + 1} {text}"

        return None

    def _table_to_markdown(self, table: Table) -> str:
        """表格转成 Markdown 形式，保留行列结构，避免被切碎后失去可读性。"""
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [self._clean_cell(cell.text).replace("\n", " ") for cell in row.cells]
            if any(cells):
                rows.append(cells)
        if not rows:
            return ""

        # 去掉完全重复的行（合并单元格会导致 python-docx 重复返回同一内容）
        deduped: list[list[str]] = []
        for row in rows:
            if not deduped or deduped[-1] != row:
                deduped.append(row)

        width = max(len(row) for row in deduped)
        lines = []
        for index, row in enumerate(deduped):
            padded = row + [""] * (width - len(row))
            lines.append("| " + " | ".join(padded) + " |")
            if index == 0:
                lines.append("|" + " --- |" * width)
        return "\n".join(lines)

    @staticmethod
    def _clean_cell(text: str) -> str:
        return _CONTROL_CHARS.sub("", text).replace("\u00a0", " ").strip()
