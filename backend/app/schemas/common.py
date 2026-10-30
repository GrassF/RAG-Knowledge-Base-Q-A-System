"""通用响应模型。

所有接口统一返回 {code, message, data, request_id}。
code=0 表示成功，非 0 见 app.core.exceptions.ErrorCode。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None
    request_id: str | None = None


def success(data: Any = None, message: str = "success") -> dict[str, Any]:
    """构造成功响应体，request_id 与日志/响应头保持一致。"""
    from app.core.logging import request_id_ctx

    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": request_id_ctx.get(),
    }
