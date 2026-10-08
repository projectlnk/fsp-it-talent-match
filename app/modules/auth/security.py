"""Утилиты безопасности: хеширование пароля, JWT, токены подтверждения email.

Модуль не знает ни о БД, ни о HTTP — только криптография и работа со строками.
Это позволяет переиспользовать функции в сервисах, роутерах и тестах без
поднятия приложения целиком.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


def _prehash(password: str) -> bytes:
    """SHA-256 пре-хеш.

    bcrypt обрезает вход старше 72 байт, что снижает энтропию длинных паролей.
    Стандартный обход — прогнать пароль через SHA-256 и уже результат подать
    в bcrypt. Это сохраняет поведение для любых длин и не ломает совместимость.
    """
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш пароля в виде строки."""
    settings = get_settings()
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    hashed = bcrypt.hashpw(_prehash(password), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против сохранённого хеша.

    Возвращает False при любых ошибках формата, чтобы не поднимать исключение
    в слое аутентификации.
    """
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str | int,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Выпускает подписанный JWT.

    subject попадает в claim `sub`. Дополнительные поля (например, role)
    можно передать через `extra`. Срок жизни — из настроек, если не задан явно.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + ttl,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Проверяет подпись и срок действия, возвращает payload.

    Поднимает jwt.InvalidTokenError, если токен некорректен или истёк.
    Обработка ошибок — на стороне вызывающего кода.
    """
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def generate_email_verification_token() -> str:
    """Случайный URL-безопасный токен для подтверждения email."""
    return secrets.token_urlsafe(32)