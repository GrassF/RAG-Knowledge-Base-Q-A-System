"""文本清洗。

原则：只做"规范化"，绝不做"删空格"这类破坏语义的操作。
早期版本用 text.replace(" ", "") 把所有空格删光，会导致英文单词粘连、
代码与表格结构被破坏，也直接让 BM25 分词失效。

这里保留空格与换行，只处理以下几类噪声：
1. 异常空白字符（全角空格、不换行空格、零宽字符、BOM）
2. PDF 换行把英文单词拆断（行尾连字符）
3. 为对齐产生的连续空格
4. 中文之间因排版产生的多余空格
5. 连续空行
"""

from __future__ import annotations

import re

# 全角空格 / 不换行空格 / 制表符
_UNICODE_SPACES = re.compile(r"[\u3000\u00a0\u1680\u2000-\u200a\u202f\u205f]")
# 零宽字符与 BOM
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
# 行内连续空白（空格/制表）压成一个空格
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
# 英文断词：re-<换行>port -> report
_HYPHEN_BREAK = re.compile(r"(?<=[A-Za-z])-\n(?=[a-z])")
# 中文与中文之间的单个空格（排版噪声）
_CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])")
# 连续空行超过 2 个压成 2 个，保留段落边界
_MULTI_BLANK = re.compile(r"\n{3,}")
# 只有标点/符号的行（PDF 分隔线等）
_MEANINGLESS_LINE = re.compile(r"^[\s\-=_*·•~—–|/\\<>\[\]()（）【】{}]+$")


def clean_text(text: str) -> str:
    """把解析得到的原始文本规范化成适合切分与检索的文本。"""
    if not text:
        return ""

    # 1. 统一换行与空白字符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH.sub("", text)
    text = _UNICODE_SPACES.sub(" ", text)

    # 2. 修复英文断词（必须在按行处理之前）
    text = _HYPHEN_BREAK.sub("", text)

    # 3. 逐行规范化，保留空行
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = _MULTI_SPACE.sub(" ", raw_line).strip()
        if not line:
            lines.append("")
            continue
        if _MEANINGLESS_LINE.match(line):
            # 分隔线、纯符号行对检索没有价值
            continue
        line = _CJK_GAP.sub("", line)
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = _MULTI_BLANK.sub("\n\n", cleaned)
    return cleaned.strip()


def has_content(text: str) -> bool:
    """是否还有实质内容（去掉空白与标点后仍有字符）。

    与 is_meaningful_chunk 的区别：这里只判断"是不是纯噪声"，
    不设长度要求，避免把"很短但有效"的内容（表格行、列表项）提前丢掉。
    """
    return bool(re.sub(r"[\s\W_]+", "", text or ""))


def is_meaningful_chunk(text: str, min_chars: int = 10) -> bool:
    """过滤掉没有信息量的切片（纯符号、极短残留）。"""
    stripped = text.strip()
    if len(stripped) < min_chars:
        return False
    # 去掉空白和标点后还剩多少内容
    meaningful = re.sub(r"[\s\W_]+", "", stripped)
    return len(meaningful) >= max(4, min_chars // 2)


def normalize_query(query: str) -> str:
    """检索前对查询做同样的规范化，保证 BM25 分词与索引侧一致。"""
    return re.sub(r"\s+", " ", _ZERO_WIDTH.sub("", query)).strip()
