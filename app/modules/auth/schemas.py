"""Pydantic-схемы модуля auth."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.auth.models import UserRole


class UserRegister(BaseModel):
    """Входные данные для регистрации."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    full_name: str | None = Field(default=None, max_length=255)


class UserLogin(BaseModel):
    """Входные данные для входа по email и паролю."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Публичное представление пользователя. Без пароля."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_email_verified: bool
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Ответ на успешный вход."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class EmailVerificationRequest(BaseModel):
    """Запрос на подтверждение email по токену."""

    token: str


class MessageResponse(BaseModel):
    """Простой ответ с текстовым сообщением."""

    message: str