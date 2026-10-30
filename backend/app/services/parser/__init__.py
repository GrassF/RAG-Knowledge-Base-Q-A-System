"""文档解析器包。"""

from app.services.parser.base import BaseParser, ParsedBlock, ParseResult  # noqa: F401
from app.services.parser.registry import get_parser, parse_file  # noqa: F401
