"""持久化层：SQLAlchemy 2.0 + SQLite。

表结构在 models.py，连接与会话在 database.py，建表在 init_db.py。
"""

from app.db.database import SessionLocal, get_db, session_scope  # noqa: F401
from app.db.models import Base, Conversation, Document, Message, User  # noqa: F401
