"""HTTP 路由汇总。

把 documents / chat / health 三个子路由聚合成 api_router，
由 main.create_app() 以 settings.api_prefix（默认 /api/v1）统一挂载。

这一层只做「参数校验 + 调 service + 包响应」，不含业务逻辑。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import chat, documents, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(documents.router)