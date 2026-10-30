"""文本清洗的单元测试。

重点是守住"绝不能删空格"这条底线——这是原实现最严重的问题。
"""

from __future__ import annotations

from app.services.cleaning import clean_text, is_meaningful_chunk, normalize_query


def test_keeps_single_spaces_between_english_words():
    assert clean_text("Hello   world") == "Hello world"
    assert " " in clean_text("vector store retrieval")


def test_removes_zero_width_characters():
    assert clean_text("知\u200b识\ufeff库") == "知识库"


def test_fixes_hyphenated_line_break():
    assert clean_text("re-\nport") == "report"
    # 中文断词不处理，保留原样
    assert clean_text("中-\n文").startswith("中-")


def test_normalizes_unicode_spaces():
    assert clean_text("a\u3000b\u00a0c") == "a b c"


def test_collapses_extra_blank_lines():
    assert clean_text("第一段\n\n\n\n第二段") == "第一段\n\n第二段"


def test_removes_separator_lines():
    assert clean_text("正文内容\n=====\n下一段") == "正文内容\n下一段"


def test_cjk_spacing_noise_removed():
    # PDF 两端对齐会在汉字之间插入空格
    assert clean_text("向 量 检 索") == "向量检索"


def test_mixed_language_keeps_space():
    assert clean_text("使用 BM25 算法") == "使用 BM25 算法"


def test_empty_input():
    assert clean_text("") == ""
    assert clean_text("   \n\n  ") == ""


def test_is_meaningful_chunk():
    assert is_meaningful_chunk("这是一段正常的知识库内容", min_chars=10)
    assert not is_meaningful_chunk("。", min_chars=10)
    assert not is_meaningful_chunk("--- ---", min_chars=10)


def test_normalize_query():
    assert normalize_query("  混合  检索\u200b ") == "混合 检索"