"""健康检查。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import RagService
from app.core.config import get_settings
from app.schemas.common import ApiResponse, success

router = APIRouter(tags=["系统"])


@router.get("/health", response_model=ApiResponse[dict], summary="健康检查")
def health(rag: RagService) -> dict:
    settings = get_settings()
    return success(
        {
            "status": "ok",
            "version": settings.app_version,
            "vector_type": settings.vector_type,
            "collection": settings.collection_name,
            "vectors": rag.vector_store.count(),
            "bm25_chunks": rag.bm25_index.size,
            "retrieval_mode": settings.retrieval_mode,
            "rerank_model": settings.rerank_model if settings.use_rerank else None,
        }
    )