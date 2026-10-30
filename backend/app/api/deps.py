"""路由依赖：数据库会话、当前登录用户、RAG 服务。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import BizException, ErrorCode
from app.core.security import decode_access_token
from app.db.database import get_db
from app.db.models import User
from app.services.container import get_rag
from app.services.rag_chain import RagChain

# auto_error=False：未带 token 时自己抛业务异常，保证返回体格式统一
bearer_scheme = HTTPBearer(auto_error=False, description="登录后返回的 access_token")


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise BizException(ErrorCode.UNAUTHORIZED)

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise BizException(ErrorCode.TOKEN_INVALID)

    user = db.get(User, int(user_id))
    if user is None:
        raise BizException(ErrorCode.TOKEN_INVALID)
    return user


DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
RagService = Annotated[RagChain, Depends(get_rag)]