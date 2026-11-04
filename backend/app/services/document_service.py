"""文档服务：上传编排与文档全生命周期管理。

上传链路：解析（parser）→ 清洗（cleaning）→ 结构感知切分（splitter）
          → 向量化入库（embedding + vector_store）→ 同步 BM25 索引
另提供：文档列表、切片预览、单篇删除、清空全部
上游：api.documents；下游：parser/*、splitter、embedding、vector_store、bm25_index
"""

from __future__ import annotations

import hashlib
import os

from langchain_core.documents import Document as LcDocument
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BizException, ErrorCode
from app.db.models import Document
from app.schemas.document import (
    ChunkPreview,
    ChunkPreviewOut,
    ClearResult,
    DocumentOut,
    UploadResult,
)
from app.services.parser import parse_file
from app.services.rag_chain import RagChain
from app.services.splitter import DocumentSplitter

CHUNK_PREVIEW_LIMIT = 200


class DocumentService:
    def __init__(self, db: Session, rag: RagChain) -> None:
        self.db = db
        self.rag = rag
        self.settings = get_settings()
        self.splitter = DocumentSplitter()

    # ===================== 上传 =====================
    def upload(self, filename: str, data: bytes) -> UploadResult:
        self._validate_file(filename, data)

        file_hash = hashlib.sha256(data).hexdigest()
        existing = self.db.scalar(select(Document).where(Document.file_hash == file_hash))
        if existing is not None:
            logger.info("文档已存在，跳过重复入库：{}（doc_id={}）", filename, existing.id)
            return UploadResult(
                doc_id=existing.id,
                filename=existing.filename,
                chunk_count=existing.chunk_count,
                page_count=0,
                section_count=0,
                status=existing.status,
                duplicated=True,
                message="该文档已在知识库中，无需重复上传",
            )

        document = Document(
            filename=filename,
            file_hash=file_hash,
            file_size=len(data),
            file_type=os.path.splitext(filename)[-1].lower(),
            status="processing",
        )
        self.db.add(document)
        self.db.flush()

        try:
            parsed = parse_file(filename, data)
            chunks = self.splitter.split(
                parsed.blocks,
                base_metadata={
                    "doc_id": document.id,
                    "filename": filename,
                    "file_type": document.file_type,
                },
            )
            if not chunks:
                raise BizException(ErrorCode.DOC_CONTENT_EMPTY)

            self.rag.vector_store.add_chunks(chunks)
            self.rag.bm25_index.add_chunks(chunks)

            document.status = "ready"
            document.chunk_count = len(chunks)
            document.error_message = None
            self.db.flush()

            logger.info(
                "文档入库完成：{}（doc_id={}, {} 页, {} 章节, {} 切片）",
                filename,
                document.id,
                parsed.page_count,
                parsed.section_count,
                len(chunks),
            )
            return UploadResult(
                doc_id=document.id,
                filename=filename,
                chunk_count=len(chunks),
                page_count=parsed.page_count,
                section_count=parsed.section_count,
                status="ready",
                message=f"上传成功，已切分为 {len(chunks)} 个片段",
            )
        except Exception as exc:
            document.status = "failed"
            document.error_message = str(exc)[:500]
            self.db.flush()
            logger.exception("文档入库失败：{}", filename)
            raise

    # ===================== 查询 =====================
    def list_documents(self) -> list[DocumentOut]:
        documents = self.db.scalars(
            select(Document).order_by(Document.created_at.desc())
        ).all()
        return [DocumentOut.model_validate(item) for item in documents]

    def get(self, doc_id: int) -> Document:
        document = self.db.get(Document, doc_id)
        if document is None:
            raise BizException(ErrorCode.DOC_NOT_FOUND)
        return document

    def list_chunks(self, doc_id: int, limit: int = CHUNK_PREVIEW_LIMIT) -> ChunkPreviewOut:
        document = self.get(doc_id)
        documents: list[LcDocument] = self.rag.vector_store.list_by_doc_id(doc_id)
        documents.sort(key=lambda item: int(item.metadata.get("chunk_index") or 0))

        items = [
            ChunkPreview(
                chunk_id=str(item.metadata.get("chunk_id") or item.id or ""),
                chunk_index=int(item.metadata.get("chunk_index") or 0),
                page=self._as_int(item.metadata.get("page")),
                section=item.metadata.get("section") or None,
                char_start=int(item.metadata.get("char_start") or 0),
                char_end=int(item.metadata.get("char_end") or 0),
                text=item.page_content,
            )
            for item in documents[:limit]
        ]
        return ChunkPreviewOut(
            doc_id=document.id,
            filename=document.filename,
            total=len(documents),
            items=items,
        )

    # ===================== 删除 =====================
    def delete(self, doc_id: int) -> dict[str, int | str]:
        document = self.get(doc_id)
        deleted_vectors = self.rag.vector_store.delete_by_doc_id(doc_id)
        deleted_tokens = self.rag.bm25_index.remove_by_doc_id(doc_id)
        self.db.delete(document)
        self.db.flush()
        logger.info(
            "文档已删除：{}（doc_id={}, 向量={}, BM25={}）",
            document.filename,
            doc_id,
            deleted_vectors,
            deleted_tokens,
        )
        return {
            "doc_id": doc_id,
            "deleted_chunks": deleted_vectors,
            "message": "删除成功",
        }

    def clear(self) -> ClearResult:
        document_ids = list(self.db.scalars(select(Document.id)).all())
        deleted_chunks = 0
        for doc_id in document_ids:
            deleted_chunks += self.rag.vector_store.delete_by_doc_id(doc_id)
            self.rag.bm25_index.remove_by_doc_id(doc_id)

        if document_ids:
            for document in self.db.scalars(select(Document)).all():
                self.db.delete(document)
        self.db.flush()

        logger.info(
            "知识库已清空：文档={} 切片={}", len(document_ids), deleted_chunks
        )
        return ClearResult(
            deleted_documents=len(document_ids),
            deleted_chunks=deleted_chunks,
            message="知识库已清空",
        )

    # ===================== 内部工具 =====================
    def _validate_file(self, filename: str, data: bytes) -> None:
        if not filename:
            raise BizException(ErrorCode.PARAM_INVALID, "缺少文件名")
        extension = os.path.splitext(filename)[-1].lower()
        if extension not in self.settings.allowed_extension_list:
            raise BizException(
                ErrorCode.FILE_TYPE_UNSUPPORTED,
                f"仅支持 {', '.join(self.settings.allowed_extension_list)} 格式",
            )
        if not data:
            raise BizException(ErrorCode.FILE_EMPTY, "文件内容为空")
        if len(data) > self.settings.max_upload_size_bytes:
            raise BizException(
                ErrorCode.FILE_TOO_LARGE,
                f"文件超过 {self.settings.max_upload_size_mb}MB 限制",
            )

    @staticmethod
    def _as_int(value) -> int | None:
        try:
            number = int(value)
            return number or None
        except (TypeError, ValueError):
            return None


def sanitize_filename(filename: str) -> str:
    """去掉路径分隔符，防止 ../ 之类的路径穿越（也用于展示侧统一格式）。"""
    name = os.path.basename(filename.replace("\\", "/"))
    for char in ('..', '/', '\\', '\x00'):
        name = name.replace(char, "")
    return name.strip() or "unnamed"

