"""Unit-тесты безопасности модуля auth: bcrypt и JWT.

БД и FastAPI не требуются, проверяется только криптография.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.modules.auth.security import (
    create_access_token,
    decode_access_token,
    generate_email_verification_token,
    hash_password,
    verify_password,
)


# --- Пароли --------------------------------------------------------------


def test_hash_password_returns_different_hashes_for_same_password():
    """Соль разная, значит и хеши разные."""
    assert hash_password("test1234") != hash_password("test1234")


def test_hash_password_does_not_contain_plaintext():
    hashed = hash_password("very-secret-password")
    assert "very-secret-password" not in hashed
    assert hashed.startswith("$2")


def test_verify_password_accepts_correct_password():
    hashed = hash_password("test1234")
    assert verify_password("test1234", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("test1234")
    assert verify_password("wrong1234", hashed) is False


def test_verify_password_rejects_garbage_hash():
    """Повреждённый хеш не должен ронять сервис исключением."""
    assert verify_password("test1234", "not-a-bcrypt-hash") is False
    assert verify_password("test1234", "") is False


def test_verify_password_handles_long_password():
    """Длинные пароли не должны обрезаться до 72 байт."""
    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed) is True
    # пароль, отличающийся только после 72-го символа, должен отвергаться
    slightly_different = "x" * 71 + "y" + "x" * 128
    assert verify_password(slightly_different, hashed) is False


# --- JWT -----------------------------------------------------------------


def test_access_token_roundtrip():
    token = create_access_token(42, extra={"role": "candidate"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "candidate"
    assert "exp" in payload
    assert "iat" in payload


def test_access_token_custom_expiry():
    token = create_access_token(1, expires_delta=timedelta(seconds=60))
    payload = decode_access_token(token)
    now = datetime.now(UTC).timestamp()
    # exp примерно через минуту
    assert 55 < payload["exp"] - now < 65


def test_expired_token_raises():
    token = create_access_token(1, expires_delta=timedelta(seconds=-10))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_signature_raises():
    token = create_access_token(1)
    tampered = token[:-4] + "AAAA"
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_token_signed_with_other_secret_raises():
    settings = get_settings()
    foreign = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "some-other-secret",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(foreign)


# --- Токен подтверждения email -------------------------------------------


def test_email_verification_token_is_unique():
    tokens = {generate_email_verification_token() for _ in range(20)}
    assert len(tokens) == 20


def test_email_verification_token_length():
    token = generate_email_verification_token()
    assert len(token) >= 32
    # URL-safe base64 без пробелов
    assert " " not in token