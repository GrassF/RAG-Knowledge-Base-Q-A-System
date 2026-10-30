"""纯文本解析：自动探测编码，按标题行切分章节。"""

from __future__ import annotations

from charset_normalizer import from_bytes
from loguru import logger

from app.services.parser.base import BaseParser, ParsedBlock, ParseResult, detect_heading, push_section


class TxtParser(BaseParser):
    extensions = (".txt", ".md")

    def parse(self, data: bytes) -> ParseResult:
        text = self._decode(data)
        blocks: list[ParsedBlock] = []
        buffer: list[str] = []
        section_stack: list[tuple[int, str]] = []
        current_section: str | None = None

        def flush() -> None:
            nonlocal buffer
            content = "\n".join(buffer).strip()
            if content:
                blocks.append(ParsedBlock(text=content, page=None, section=current_section))
            buffer = []

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                if buffer and buffer[-1] != "":
                    buffer.append("")
                continue

            heading = detect_heading(line)
            if heading:
                flush()
                current_section = push_section(section_stack, heading)
                blocks.append(
                    ParsedBlock(text=heading, page=None, section=current_section, kind="heading")
                )
                continue

            buffer.append(line)

        flush()
        logger.info("TXT 解析完成：{} 个文本块，{} 个章节", len(blocks), len(section_stack))
        return ParseResult(blocks=blocks, page_count=0)

    @staticmethod
    def _decode(data: bytes) -> str:
        """优先 utf-8；失败后用 charset-normalizer 探测（兼容 GBK/GB18030）。"""
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            best = from_bytes(data).best()
            if best is None:
                return data.decode("utf-8", errors="replace")
            return str(best)
