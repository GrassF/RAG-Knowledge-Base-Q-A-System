"""日志配置：loguru 为主，拦截标准库 logging 统一输出。

机制：setup_logging() 配置控制台与文件输出（按天切分、保留份数、压缩）；
      _patch_record() 把 request_id 注入每条日志，便于按请求串联排查
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

from loguru import logger

from app.core.config import get_settings

# 每个请求一个唯一 ID，由中间件写入，日志自动带上
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_CONFIGURED = False


class _InterceptHandler(logging.Handler):
    """把标准库 logging 的记录转发给 loguru。"""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - 简单转发
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _patch_record(record: dict) -> None:
    record["extra"].setdefault("request_id", request_id_ctx.get())


def setup_logging() -> None:
    """初始化日志，重复调用无副作用。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    settings.log_path.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.configure(patcher=_patch_record)

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[request_id]}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        format=log_format,
        colorize=True,
        backtrace=settings.debug,
        diagnose=settings.debug,
    )
    # 落盘：按天切割，保留 14 天，异步写入减少阻塞
    logger.add(
        settings.log_path / "app_{time:YYYY-MM-DD}.log",
        level=settings.log_level.upper(),
        format=log_format.replace("<green>", "").replace("</green>", "")
        .replace("<level>", "").replace("</level>", "")
        .replace("<cyan>", "").replace("</cyan>", ""),
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    # 接管 uvicorn 与标准库日志
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        std_logger = logging.getLogger(name)
        std_logger.handlers = [_InterceptHandler()]
        std_logger.propagate = False

    _CONFIGURED = True
