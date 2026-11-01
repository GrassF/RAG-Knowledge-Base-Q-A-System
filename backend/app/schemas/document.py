"""文档模型：上传结果、文档列表项、切片预览、清空结果。

DocumentOut：单篇文档的元信息与切片数
UploadResult：上传完成后的切片统计
ChunkPreview / ChunkPreviewOut：切片正文 + 页码 + 章节，用于入库后核对切分效果
ClearResult：清空操作实际删除的文档数与切片数
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size: int
    file_type: str
    status: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime


class UploadResult(BaseModel):
    doc_id: int
    filename: str
    chunk_count: int
    page_count: int
    section_count: int
    status: str
    duplicated: bool = False
    message: str = "上传成功"


class ChunkPreview(BaseModel):
    """单个切片的预览，用于前端查看切分效果。"""

    chunk_id: str
    chunk_index: int
    page: int | None = None
    section: str | None = None
    char_start: int = 0
    char_end: int = 0
    text: str


class ChunkPreviewOut(BaseModel):
    doc_id: int
    filename: str
    total: int
    items: list[ChunkPreview]


class ClearResult(BaseModel):
    deleted_documents: int
    deleted_chunks: int
    message: str = "知识库已清空"
