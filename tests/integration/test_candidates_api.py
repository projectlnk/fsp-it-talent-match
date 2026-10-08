"""Интеграционные тесты API профиля кандидата."""
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
PREFIX = "cand-test-"


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


def _register_and_login(client, email, role="candidate", full_name="Test User") -> str:
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


# --- Доступ -------------------------------------------------------------


def test_get_me_requires_auth(client):
    r = client.get("/api/v1/candidates/me")
    assert r.status_code == 401


def test_get_me_rejects_employer(client):
    token = _register_and_login(client, _email(), role="employer", full_name="ACME")
    r = client.get("/api/v1/candidates/me", headers=_auth(token))
    assert r.status_code == 403


# --- Профиль ------------------------------------------------------------


def test_get_empty_profile(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.get("/api/v1/candidates/me", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skills"] == []
    assert body["experiences"] == []


def test_patch_profile(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.patch(
        "/api/v1/candidates/me",
        headers=_auth(token),
        json={
            "desired_role": "Backend",
            "desired_salary_from": 150000,
            "desired_salary_to": 250000,
            "work_format": "remote",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["desired_role"] == "Backend"
    assert body["work_format"] == "remote"

    # сохраняется после повторного GET
    r2 = client.get("/api/v1/candidates/me", headers=_auth(token))
    assert r2.json()["desired_role"] == "Backend"


def test_patch_profile_validates_salary_range(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.patch(
        "/api/v1/candidates/me",
        headers=_auth(token),
        json={"desired_salary_from": 300000, "desired_salary_to": 100000},
    )
    assert r.status_code == 422


def test_patch_profile_partial_update_keeps_other_fields(client):
    email = _email()
    token = _register_and_login(client, email)
    client.patch(
        "/api/v1/candidates/me",
        headers=_auth(token),
        json={"desired_role": "Backend", "location": "Москва"},
    )
    r = client.patch(
        "/api/v1/candidates/me",
        headers=_auth(token),
        json={"location": "Санкт-Петербург"},
    )
    assert r.json()["desired_role"] == "Backend"
    assert r.json()["location"] == "Санкт-Петербург"


# --- Навыки -------------------------------------------------------------


def test_add_skill(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.post(
        "/api/v1/candidates/me/skills",
        headers=_auth(token),
        json={"skill": "Python", "level": "senior"},
    )
    assert r.status_code == 201, r.text
    skills = r.json()["skills"]
    assert len(skills) == 1
    assert skills[0]["skill"] == "Python"
    assert skills[0]["level"] == "senior"


def test_add_duplicate_skill_returns_409(client):
    email = _email()
    token = _register_and_login(client, email)
    client.post(
        "/api/v1/candidates/me/skills",
        headers=_auth(token),
        json={"skill": "Python"},
    )
    r = client.post(
        "/api/v1/candidates/me/skills",
        headers=_auth(token),
        json={"skill": "Python"},
    )
    assert r.status_code == 409


def test_delete_skill(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.post(
        "/api/v1/candidates/me/skills",
        headers=_auth(token),
        json={"skill": "Python"},
    )
    skill_id = r.json()["skills"][0]["id"]
    r = client.delete(
        f"/api/v1/candidates/me/skills/{skill_id}",
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["skills"] == []


def test_delete_foreign_skill_returns_404(client):
    email1, email2 = _email(), _email()
    token1 = _register_and_login(client, email1)
    token2 = _register_and_login(client, email2)
    r = client.post(
        "/api/v1/candidates/me/skills",
        headers=_auth(token1),
        json={"skill": "Python"},
    )
    skill_id = r.json()["skills"][0]["id"]

    # второй кандидат пытается удалить чужой навык
    r2 = client.delete(
        f"/api/v1/candidates/me/skills/{skill_id}",
        headers=_auth(token2),
    )
    assert r2.status_code == 404


# --- Опыт ---------------------------------------------------------------


def test_add_experience(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.post(
        "/api/v1/candidates/me/experiences",
        headers=_auth(token),
        json={
            "company_name": "ACME",
            "position": "Backend Dev",
            "started_at": "2022-01-01",
            "is_current": True,
        },
    )
    assert r.status_code == 201, r.text
    experiences = r.json()["experiences"]
    assert len(experiences) == 1
    assert experiences[0]["company_name"] == "ACME"


def test_delete_experience(client):
    email = _email()
    token = _register_and_login(client, email)
    r = client.post(
        "/api/v1/candidates/me/experiences",
        headers=_auth(token),
        json={"company_name": "ACME", "position": "Dev"},
    )
    exp_id = r.json()["experiences"][0]["id"]
    r = client.delete(
        f"/api/v1/candidates/me/experiences/{exp_id}",
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["experiences"] == []