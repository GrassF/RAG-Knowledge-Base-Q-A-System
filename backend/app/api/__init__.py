"""API 路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import auth, chat, documents, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)