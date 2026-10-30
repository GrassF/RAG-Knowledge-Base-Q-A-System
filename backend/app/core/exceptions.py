"""统一错误码与异常体系。

约定：业务错误一律通过 BizException 抛出，由全局处理器转成
{code, message, data, request_id} 结构，前端只认 code 字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx


@dataclass(frozen=True)
class ErrorDef:
    """一个错误定义：业务码 + 默认文案 + HTTP 状态码。"""

    code: int
    message: str
    http_status: int = 400


class ErrorCode:
    """全局错误码表。业务码按模块分段，便于前端分支处理。"""

    OK = ErrorDef(0, "success", 200)

    # 通用 4xxx
    PARAM_INVALID = ErrorDef(4000, "请求参数不合法", 400)
    UNAUTHORIZED = ErrorDef(4010, "未登录或登录状态已失效", 401)
    TOKEN_INVALID = ErrorDef(4011, "登录凭证无效", 401)
    TOKEN_EXPIRED = ErrorDef(4012, "登录已过期，请重新登录", 401)
    FORBIDDEN = ErrorDef(4030, "没有权限访问该资源", 403)
    NOT_FOUND = ErrorDef(4040, "资源不存在", 404)
    METHOD_NOT_ALLOWED = ErrorDef(4050, "请求方法不被允许", 405)

    # 用户 41xx
    USERNAME_EXISTS = ErrorDef(4100, "用户名已被注册", 409)
    USER_NOT_FOUND = ErrorDef(4101, "用户不存在", 404)
    PASSWORD_ERROR = ErrorDef(4102, "用户名或密码错误", 401)

    # 文档 42xx
    FILE_TYPE_UNSUPPORTED = ErrorDef(4200, "不支持的文件类型", 415)
    FILE_TOO_LARGE = ErrorDef(4201, "文件大小超出限制", 413)
    FILE_EMPTY = ErrorDef(4202, "文件内容为空", 422)
    DOC_NOT_FOUND = ErrorDef(4203, "文档不存在", 404)
    DOC_DUPLICATED = ErrorDef(4204, "该文档已存在于知识库", 409)
    DOC_PARSE_FAILED = ErrorDef(4205, "文档解析失败", 422)
    DOC_CONTENT_EMPTY = ErrorDef(4206, "未能从文档中提取到有效文本", 422)

    # 会话 43xx
    CONVERSATION_NOT_FOUND = ErrorDef(4310, "会话不存在", 404)

    # 检索 / 模型 5xxx
    INTERNAL_ERROR = ErrorDef(5000, "服务器内部错误", 500)
    LLM_ERROR = ErrorDef(5001, "大模型调用失败", 502)
    RERANK_FAILED = ErrorDef(5002, "重排序服务调用失败", 502)
    EMBEDDING_FAILED = ErrorDef(5003, "向量化服务调用失败", 502)
    INDEX_ERROR = ErrorDef(5004, "索引操作失败", 500)
    RATE_LIMITED = ErrorDef(5029, "请求过于频繁，请稍后再试", 429)


class BizException(Exception):
    """业务异常。捕获后返回统一结构，不打印堆栈。"""

    def __init__(
        self,
        error: ErrorDef = ErrorCode.INTERNAL_ERROR,
        message: str | None = None,
        data: Any = None,
    ) -> None:
        self.error = error
        self.code = error.code
        self.message = message or error.message
        self.http_status = error.http_status
        self.data = data
        super().__init__(self.message)


def _payload(code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id_ctx.get(),
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizException)
    async def _biz_handler(request: Request, exc: BizException) -> JSONResponse:
        logger.warning(
            "业务异常 {} {} -> code={} message={}", request.method, request.url.path, exc.code, exc.message
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # 把 pydantic 的错误压平成一句人话，便于前端直接提示
        details = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
            details.append(f"{location}: {item.get('msg', '参数错误')}")
        message = "；".join(details) or ErrorCode.PARAM_INVALID.message
        logger.warning("参数校验失败 {} {} -> {}", request.method, request.url.path, message)
        return JSONResponse(
            status_code=ErrorCode.PARAM_INVALID.http_status,
            content=_payload(ErrorCode.PARAM_INVALID.code, message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # 保留 404/405 等框架级错误的原始状态码
        code = 4000 + exc.status_code if exc.status_code >= 400 else ErrorCode.INTERNAL_ERROR.code
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未捕获异常 {} {} -> {}", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content=_payload(ErrorCode.INTERNAL_ERROR.code, ErrorCode.INTERNAL_ERROR.message),
        )
