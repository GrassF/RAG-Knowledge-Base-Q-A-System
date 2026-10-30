"""文档管理接口：上传、列表、切片预览、删除、清空。"""

from __future__ import annotations

from fastapi import APIRouter, File, Path, UploadFile

from app.api.deps import CurrentUser, DbSession, RagService
from app.schemas.common import ApiResponse, success
from app.schemas.document import (
    ChunkPreviewOut,
    ClearResult,
    DocumentOut,
    UploadResult,
)
from app.services.document_service import DocumentService, sanitize_filename

router = APIRouter(prefix="/documents", tags=["文档"])


@router.post(
    "/upload",
    response_model=ApiResponse[UploadResult],
    summary="上传文档并入库（TXT / PDF / DOCX）",
)
def upload_document(
    user: CurrentUser,
    db: DbSession,
    rag: RagService,
    file: UploadFile = File(..., description="待上传的文档"),
) -> dict:
    # 同步端点：FastAPI 会自动放到线程池执行，不会阻塞事件循环
    data = file.file.read()
    filename = sanitize_filename(file.filename or "")
    result = DocumentService(db, rag).upload(user.id, filename, data)
    db.commit()
    return success(result)


@router.get(
    "",
    response_model=ApiResponse[list[DocumentOut]],
    summary="当前用户的知识库文档列表",
)
def list_documents(user: CurrentUser, db: DbSession, rag: RagService) -> dict:
    return success(DocumentService(db, rag).list_documents(user.id))


@router.get(
    "/{doc_id}/chunks",
    response_model=ApiResponse[ChunkPreviewOut],
    summary="查看某个文档的切片（调参用）",
)
def list_chunks(
    user: CurrentUser,
    db: DbSession,
    rag: RagService,
    doc_id: int = Path(ge=1),
) -> dict:
    return success(DocumentService(db, rag).list_chunks(user.id, doc_id))


@router.delete(
    "/{doc_id}",
    response_model=ApiResponse[dict],
    summary="删除文档（同步清理向量库与 BM25 索引）",
)
def delete_document(
    user: CurrentUser,
    db: DbSession,
    rag: RagService,
    doc_id: int = Path(ge=1),
) -> dict:
    result = DocumentService(db, rag).delete(user.id, doc_id)
    db.commit()
    return success(result)


@router.post(
    "/clear",
    response_model=ApiResponse[ClearResult],
    summary="清空当前用户的知识库",
)
def clear_documents(user: CurrentUser, db: DbSession, rag: RagService) -> dict:
    result = DocumentService(db, rag).clear(user.id)
    db.commit()
    return success(result)