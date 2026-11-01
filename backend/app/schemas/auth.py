"""鉴权模型：注册/登录请求体，用户信息与 Token 响应体。

RegisterRequest / LoginRequest：用户名 + 密码，带长度与格式校验
UserOut：对外暴露的用户信息，不含密码哈希
TokenOut：JWT 字符串与其过期时间
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, description="3-32 位用户名")
    password: str = Field(min_length=6, max_length=64, description="6-64 位密码")

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("用户名不能为空")
        if not value.replace("_", "").isalnum():
            raise ValueError("用户名只能包含字母、数字和下划线")
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=64)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        return value.strip()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
