"""文档管理相关的请求/响应模型。"""

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
