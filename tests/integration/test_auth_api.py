"""Интеграционные тесты JSON API аутентификации.

Требуют запущенного Compose и RUN_INTEGRATION=1. Работают через HTTP к
приложению и через прямое подключение к БД для подготовки и очистки данных.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.models import EmailVerificationToken, User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
PREFIX = "auth-test-"


def _email() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(autouse=True)
def cleanup():
    """Удаляет все тестовые пользователи после каждого теста."""
    yield
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email.like(f"{PREFIX}%")))
        session.commit()


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


def _register(client, email, password="test1234", role="candidate", full_name="Test User"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "role": role,
            "full_name": full_name,
        },
    )


def _login(client, email, password="test1234"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def _get_verification_token(email: str) -> str:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None, f"user {email} not found"
        record = session.scalar(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.user_id == user.id)
            .order_by(EmailVerificationToken.id.desc())
        )
        assert record is not None
        return record.token


# --- Регистрация ---------------------------------------------------------


def test_register_returns_201_with_user(client):
    email = _email()
    r = _register(client, email)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == email
    assert body["role"] == "candidate"
    assert body["is_email_verified"] is False
    # пароль не должен утечь
    assert "password" not in body
    assert "password_hash" not in body


def test_register_duplicate_returns_409(client):
    email = _email()
    assert _register(client, email).status_code == 201
    r = _register(client, email)
    assert r.status_code == 409


def test_register_normalizes_email_case(client):
    email = _email()
    assert _register(client, email.upper()).status_code == 201
    assert _register(client, email.lower()).status_code == 409


def test_register_rejects_short_password(client):
    r = _register(client, _email(), password="short")
    assert r.status_code == 422


def test_register_rejects_invalid_email(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "test1234", "role": "candidate"},
    )
    assert r.status_code == 422


def test_register_creates_candidate_profile(client):
    from app.modules.candidates.models import CandidateProfile

    email = _email()
    _register(client, email, role="candidate")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        profile = session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user.id)
        )
        assert profile is not None


def test_register_creates_employer_profile(client):
    from app.modules.employers.models import EmployerProfile

    email = _email()
    _register(client, email, role="employer", full_name="ACME Corp")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        profile = session.scalar(
            select(EmployerProfile).where(EmployerProfile.user_id == user.id)
        )
        assert profile is not None
        assert profile.company_name == "ACME Corp"


# --- Вход ----------------------------------------------------------------


def test_login_returns_token(client):
    email = _email()
    _register(client, email)
    r = _login(client, email)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_wrong_password_returns_401(client):
    email = _email()
    _register(client, email)
    r = _login(client, email, password="wrong1234")
    assert r.status_code == 401


def test_login_unknown_email_returns_401(client):
    r = _login(client, _email())
    assert r.status_code == 401


# --- /me -----------------------------------------------------------------


def test_me_without_token_returns_401(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_garbage_token_returns_401(client):
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert r.status_code == 401


def test_me_with_valid_token_returns_user(client):
    email = _email()
    _register(client, email)
    token = _login(client, email).json()["access_token"]
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == email


# --- Подтверждение email -------------------------------------------------


def test_verify_email_with_valid_token(client):
    email = _email()
    _register(client, email)
    token = _get_verification_token(email)

    r = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert "подтверждён" in r.json()["message"].lower()

    # повторное использование запрещено
    r2 = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert r2.status_code == 400

    # /me отражает новое состояние
    access = _login(client, email).json()["access_token"]
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert me.json()["is_email_verified"] is True


def test_verify_email_with_invalid_token_returns_400(client):
    r = client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
    assert r.status_code == 400


def test_register_sends_mail_to_mailpit(client):
    email = _email()
    _register(client, email)

    mailpit = os.getenv("MAILPIT_BASE_URL", "http://mailpit:8025")
    r = httpx.get(f"{mailpit}/api/v1/messages", timeout=10)
    assert r.status_code == 200

    messages = r.json().get("messages", [])
    matching = [
        m
        for m in messages
        if any(
            (addr.get("Address") or "").lower() == email.lower()
            for addr in (m.get("To") or [])
        )
    ]
    assert matching, f"no email found in Mailpit for {email}"