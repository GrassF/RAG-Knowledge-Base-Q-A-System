"""解析器注册表：按扩展名分发。"""

from __future__ import annotations

import os
from functools import lru_cache

from app.core.exceptions import BizException, ErrorCode
from app.services.parser.base import BaseParser, ParseResult
from app.services.parser.docx_parser import DocxParser
from app.services.parser.pdf_parser import PdfParser
from app.services.parser.txt_parser import TxtParser

_PARSERS: tuple[BaseParser, ...] = (PdfParser(), DocxParser(), TxtParser())

# 明确不支持的格式，给出可操作的提示
_HINT_MESSAGES = {
    ".doc": "暂不支持 .doc 老格式，请在 Word 中另存为 .docx 后重新上传",
    ".xls": "暂不支持 .xls 老格式，请另存为 .xlsx 或导出为 .pdf/.txt",
    ".png": "图片文档暂不支持，请先使用 OCR 转成文本",
}


@lru_cache(maxsize=32)
def get_parser(extension: str) -> BaseParser:
    extension = extension.lower()
    for parser in _PARSERS:
        if extension in parser.extensions:
            return parser
    hint = _HINT_MESSAGES.get(extension, f"不支持的文件类型：{extension or '未知'}")
    raise BizException(ErrorCode.FILE_TYPE_UNSUPPORTED, hint)


def parse_file(filename: str, data: bytes) -> ParseResult:
    extension = os.path.splitext(filename)[-1].lower()
    parser = get_parser(extension)
    result = parser.parse(data)
    if result.is_empty:
        raise BizException(ErrorCode.DOC_CONTENT_EMPTY, "未能从文档中提取到有效文本，请检查文件内容")
    return result
