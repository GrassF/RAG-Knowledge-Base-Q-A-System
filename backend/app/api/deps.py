"""路由依赖：通过 Depends() 向业务路由注入公共依赖。

提供：get_db()（数据库会话）、get_rag()（全局唯一的 RagChain 实例）
位置：被 documents / chat / health 三个路由文件引用
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.container import get_rag
from app.services.rag_chain import RagChain

DbSession = Annotated[Session, Depends(get_db)]
RagService = Annotated[RagChain, Depends(get_rag)]
