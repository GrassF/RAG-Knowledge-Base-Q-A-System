"""鉴权接口：注册、登录、当前用户。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import BizException, ErrorCode
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.schemas.common import ApiResponse, success

router = APIRouter(prefix="/auth", tags=["鉴权"])


@router.post("/register", response_model=ApiResponse[TokenOut], summary="注册并直接登录")
def register(payload: RegisterRequest, db: DbSession) -> dict:
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists is not None:
        raise BizException(ErrorCode.USERNAME_EXISTS)

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token, expires_in = create_access_token(user.id, user.username)
    return success(
        TokenOut(
            access_token=token,
            expires_in=expires_in,
            user=UserOut.model_validate(user),
        )
    )


@router.post("/login", response_model=ApiResponse[TokenOut], summary="登录")
def login(payload: LoginRequest, db: DbSession) -> dict:
    user = db.scalar(select(User).where(User.username == payload.username))
    # 用户名不存在与密码错误返回同一个提示，避免枚举用户
    if user is None or not verify_password(payload.password, user.password_hash):
        raise BizException(ErrorCode.PASSWORD_ERROR)

    token, expires_in = create_access_token(user.id, user.username)
    return success(
        TokenOut(
            access_token=token,
            expires_in=expires_in,
            user=UserOut.model_validate(user),
        )
    )


@router.get("/me", response_model=ApiResponse[UserOut], summary="当前登录用户")
def me(user: CurrentUser) -> dict:
    return success(UserOut.model_validate(user))