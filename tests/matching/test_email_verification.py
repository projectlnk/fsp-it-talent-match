from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from app.core import email
from app.core.config import get_settings
from app.modules.auth.models import EmailVerificationToken, User
from app.modules.auth import service


@pytest.fixture(autouse=True)
def smtp(monkeypatch):
    factory = MagicMock()
    connection = factory.return_value.__enter__.return_value
    connection.send_message.return_value = {}
    monkeypatch.setattr(email.smtplib, "SMTP", factory)
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", factory)
    monkeypatch.setattr(get_settings(), "bcrypt_rounds", 4)
    monkeypatch.setattr(get_settings(), "app_base_url", "https://public.example.com/")
    return connection


def register(client):
    return client.post("/api/v1/auth/register", json={"email": "verification@example.com", "password": "test1234", "role": "candidate"})


def token(database):
    with Session(database[0]) as session:
        user = session.scalar(select(User).where(User.email == "verification@example.com"))
        return session.scalar(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id).order_by(EmailVerificationToken.id.desc())).token


def auth(client):
    result = client.post("/api/v1/auth/login", json={"email": "verification@example.com", "password": "test1234"})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def test_primary_resend_and_single_use(client, database, smtp):
    assert register(client).status_code == 201
    first = token(database)
    msg = smtp.send_message.call_args.args[0]
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "https://public.example.com/auth/verify?token=" + first in body
    assert "24 ч." in body
    assert client.post("/api/v1/auth/resend-verification", headers=auth(client)).status_code == 200
    second = token(database)
    assert first != second
    assert smtp.send_message.call_count == 2
    assert client.get("/auth/verify", params={"token": second}).status_code == 200
    repeated = client.get("/auth/verify", params={"token": second})
    assert repeated.status_code == 400 and "уже подтверждён" in repeated.text
    assert client.post("/api/v1/auth/verify-email", json={"token": second}).status_code == 400
    response = client.post("/api/v1/auth/resend-verification", headers=auth(client))
    assert response.json()["message"] == "Email уже подтверждён"
    assert smtp.send_message.call_count == 2


def test_failure_account_survives_and_resend_recovers(client, database, smtp):
    smtp.send_message.side_effect = OSError("private credentials")
    result = register(client)
    assert result.status_code == 503 and "Аккаунт создан" in result.json()["detail"]
    assert "private credentials" not in result.text
    headers = auth(client)
    assert client.post("/api/v1/auth/resend-verification", headers=headers).status_code == 503
    html = client.post("/auth/resend-verification", headers=headers)
    assert html.status_code == 503 and "Письмо не отправлено" in html.text
    smtp.send_message.side_effect = None
    assert client.post("/auth/resend-verification", headers=headers).status_code == 200
    assert client.get("/auth/verify", params={"token": token(database)}).status_code == 200


def test_html_registration_failure(client, smtp):
    smtp.send_message.side_effect = OSError("private")
    result = client.post("/auth/register", data={"email": "html@example.com", "password": "test1234", "role": "candidate"})
    assert result.status_code == 503 and "Аккаунт создан, но письмо не отправлено" in result.text
    assert "/auth/login?next=/auth/check-email" in result.text


def test_invalid_expired_and_missing_links(client, database):
    assert register(client).status_code == 201
    value = token(database)
    with Session(database[0]) as session:
        record = session.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token == value))
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert "Ссылка истекла" in client.get("/auth/verify", params={"token": value}).text
    assert client.post("/api/v1/auth/verify-email", json={"token": value}).status_code == 400
    for params in ({}, {"token": "not-valid"}):
        response = client.get("/auth/verify", params=params)
        assert response.status_code == 400 and "Ссылка недействительна" in response.text
    assert client.post("/api/v1/auth/resend-verification").status_code == 401


def test_url_encoding(smtp):
    service._send_verification_email(User(email="url@example.com"), "a&b+ /?")
    msg = smtp.send_message.call_args.args[0]
    text = msg.get_body(preferencelist=("plain",)).get_content()
    link = next(line for line in text.splitlines() if line.startswith("https://"))
    assert urlparse(link).path == "/auth/verify"
    assert parse_qs(urlparse(link).query) == {"token": ["a&b+ /?"]}


# Reuse existing API assertions with an isolated DB and mocked SMTP.
spec = importlib.util.spec_from_file_location("existing_auth_api", Path(__file__).parents[1] / "integration/test_auth_api.py")
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)
API_CASES = [name for name in vars(existing) if name.startswith("test_") and "mailpit" not in name and "email_sent" not in name]

@pytest.mark.parametrize("case", API_CASES)
def test_existing_auth_api(case, client, database, monkeypatch):
    monkeypatch.setattr(existing, "SessionLocal", sessionmaker(bind=database[0]))
    getattr(existing, case)(client)
