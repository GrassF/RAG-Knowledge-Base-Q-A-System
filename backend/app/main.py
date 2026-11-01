"""FastAPI 应用入口。

启动：在 backend/ 目录下执行 uvicorn app.main:app --reload --port 8000
接口文档：http://127.0.0.1:8000/docs
装配顺序：日志 → 中间件 → 异常处理 → 路由 → 启动钩子（建表 + 初始化服务）
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from loguru import logger

from app.api import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.db.init_db import init_db
from app.schemas.common import success
from app.services.container import init_services, shutdown_services

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging() #日志部分跳过了
    logger.info("启动 {} v{}", settings.app_name, settings.app_version)

    if not settings.dashscope_api_key or settings.dashscope_api_key == "xxx":
        logger.warning(
            "DASHSCOPE_API_KEY 未配置或仍是占位值，问答与文档入库都会失败，"
            "请在 backend/.env 中填入真实 Key"
        )

    init_db()
    init_services()
    logger.info("服务启动完成，接口文档：http://127.0.0.1:{}/docs", settings.port)

    yield

    shutdown_services()
    logger.info("服务已关闭")


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "混合检索（向量 + BM25 + RRF）与重排序的 RAG 知识库问答系统。\n\n"
            "所有接口统一返回 `{code, message, data, request_id}`，code=0 表示成功。"
        ),
        lifespan=lifespan,
        debug=settings.debug,
    )

    # 注意中间件顺序：后添加的在最外层，RequestContext 必须在最外层，
    # 这样后续中间件与业务日志都能拿到 request_id。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse(url="/docs")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return success({"status": "ok"})

    return app


app = create_app()