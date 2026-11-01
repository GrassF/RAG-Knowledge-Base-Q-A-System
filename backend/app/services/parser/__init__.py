"""文档解析器包：把 PDF / DOCX / TXT 统一解析成 ParsedBlock 列表。

对外转发：BaseParser、ParsedBlock、ParseResult、get_parser、parse_file
"""

from app.services.parser.base import BaseParser, ParsedBlock, ParseResult  # noqa: F401
from app.services.parser.registry import get_parser, parse_file  # noqa: F401
