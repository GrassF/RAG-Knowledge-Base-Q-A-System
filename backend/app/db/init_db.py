"""建表工具。应用启动时调用 init_db()，保证表结构存在。"""

from __future__ import annotations

from loguru import logger

from app.core.config import get_settings
from app.db.database import engine
from app.db.models import Base


def init_db() -> None:
    settings = get_settings()
    settings.data_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("SQLite 表结构已就绪：{}", settings.sqlite_path)


if __name__ == "__main__":  # pragma: no cover
    init_db()
