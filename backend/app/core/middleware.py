"""ASGI 中间件：请求上下文、访问日志、限流。

这里刻意使用纯 ASGI 中间件而不是 BaseHTTPMiddleware：
BaseHTTPMiddleware 会包裹 StreamingResponse，容易破坏 SSE 的边推边发行为。
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from loguru import logger
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import ErrorCode
from app.core.logging import request_id_ctx

# 不记录访问日志的路径（健康检查会被负载均衡频繁调用）
_SILENT_PATHS = {"/api/v1/health", "/favicon.ico"}


class RequestContextMiddleware:
    """生成/透传 X-Request-ID，并记录每个请求的状态码与耗时。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers") or [])
        request_id = incoming.get(b"x-request-id", b"").decode("latin-1").strip()
        request_id = request_id or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        started_at = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            path = scope.get("path", "")
            if path not in _SILENT_PATHS:
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                logger.info(
                    "{} {} -> {} ({:.1f}ms)",
                    scope.get("method", "-"),
                    path,
                    status_code,
                    elapsed_ms,
                )
            request_id_ctx.reset(token)


class RateLimitMiddleware:
    """按客户端 IP 的滑动窗口限流，默认关闭。

    单进程内存实现，够用且无额外依赖；多副本部署时应替换为 Redis。
    """

    def __init__(
        self,
        app: ASGIApp,
        limit_per_minute: int,
        protected_prefixes: tuple[str, ...] = ("/api/v1/chat",),
    ) -> None:
        if limit_per_minute <= 0:
            raise ValueError("limit_per_minute 必须大于 0")
        self.app = app
        self.limit = limit_per_minute
        self.window_seconds = 60.0
        self.protected_prefixes = protected_prefixes
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, scope: Scope) -> str:
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _hit(self, key: str) -> bool:
        """记录一次请求，返回是否超限。"""
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return True
        bucket.append(now)
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.protected_prefixes):
            await self.app(scope, receive, send)
            return

        if self._hit(self._client_key(scope)):
            response = JSONResponse(
                status_code=ErrorCode.RATE_LIMITED.http_status,
                content={
                    "code": ErrorCode.RATE_LIMITED.code,
                    "message": ErrorCode.RATE_LIMITED.message,
                    "data": None,
                    "request_id": request_id_ctx.get(),
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
