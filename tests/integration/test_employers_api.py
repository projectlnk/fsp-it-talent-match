"""Интеграционные тесты API профиля работодателя."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.modules.auth.models import User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
PREFIX = "emp-test-"


def _email() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email.like(f"{PREFIX}%")))
        session.commit()


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


def _register_and_login(client, email, role="employer", full_name="ACME") -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "test1234", "role": role, "full_name": full_name},
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "test1234"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_me_requires_auth(client):
    r = client.get("/api/v1/employers/me")
    assert r.status_code == 401


def test_get_me_rejects_candidate(client):
    token = _register_and_login(client, _email(), role="candidate", full_name="Иван")
    r = client.get("/api/v1/employers/me", headers=_auth(token))
    assert r.status_code == 403


def test_get_profile(client):
    email = _email()
    token = _register_and_login(client, email, full_name="ООО Тест")
    r = client.get("/api/v1/employers/me", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["company_name"] == "ООО Тест"


def test_patch_profile(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.patch(
        "/api/v1/employers/me",
        headers=_auth(token),
        json={
            "description": "Разработка сервисов",
            "industry": "IT",
            "contact_email": "hr@example.ru",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["industry"] == "IT"
    assert body["contact_email"] == "hr@example.ru"


def test_patch_profile_invalid_email(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.patch(
        "/api/v1/employers/me",
        headers=_auth(token),
        json={"contact_email": "not-an-email"},
    )
    assert r.status_code == 422


def test_patch_profile_partial_keeps_other_fields(client):
    email = _email()
    token = _register_and_login(client, email)
    client.patch(
        "/api/v1/employers/me",
        headers=_auth(token),
        json={"industry": "IT", "website": "https://example.ru"},
    )
    r = client.patch(
        "/api/v1/employers/me",
        headers=_auth(token),
        json={"industry": "Финтех"},
    )
    assert r.json()["industry"] == "Финтех"
    assert r.json()["website"] == "https://example.ru"


def test_candidate_cannot_patch_employer(client):
    token = _register_and_login(client, _email(), role="candidate", full_name="Иван")
    r = client.patch(
        "/api/v1/employers/me",
        headers=_auth(token),
        json={"industry": "IT"},
    )
    assert r.status_code == 403