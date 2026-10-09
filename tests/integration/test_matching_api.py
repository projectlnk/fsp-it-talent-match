"""Интеграционные тесты JSON API поиска кандидатов."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.assessments.models import (
    CandidateCategory,
    Category,
    CategoryStatus,
    Grade,
    Specialization,
)
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
PREFIX = "match-api-"


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
    with httpx.Client(base_url=BASE_URL, timeout=15) as c:
        yield c


def _register_and_login(client, email, role) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "test1234", "role": role, "full_name": "T"},
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "test1234"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_confirmed_candidate(email: str, spec: str = "backend", grade: str = "junior") -> int:
    """Создаёт кандидата с подтверждённой категорией. Возвращает profile_id."""
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        profile = session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user.id)
        )
        profile.is_searchable = True
        s = session.scalar(select(Specialization).where(Specialization.code == spec))
        g = session.scalar(select(Grade).where(Grade.code == grade))
        cat = session.scalar(
            select(Category).where(
                Category.specialization_id == s.id, Category.grade_id == g.id
            )
        )
        session.add(
            CandidateCategory(
                candidate_profile_id=profile.id,
                category_id=cat.id,
                status=CategoryStatus.CONFIRMED,
                is_current=True,
                test_score=80,
            )
        )
        session.commit()
        return profile.id


# --- Доступ --------------------------------------------------------------


def test_requires_auth(client):
    r = client.get("/api/v1/matching/candidates")
    assert r.status_code == 401


def test_candidate_forbidden(client):
    token = _register_and_login(client, _email(), "candidate")
    r = client.get("/api/v1/matching/candidates", headers=_auth(token))
    assert r.status_code == 403


# --- Поиск ---------------------------------------------------------------


def test_search_returns_confirmed_candidates(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    _make_confirmed_candidate(cand_email, "backend", "junior")

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        "/api/v1/matching/candidates",
        headers=_auth(emp_token),
        params={"specialization": "backend", "grade": "junior"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] >= 1
    assert any(c["specialization_code"] == "backend" for c in body["items"])


def test_search_result_has_match_reasons(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    _make_confirmed_candidate(cand_email, "backend", "junior")

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        "/api/v1/matching/candidates",
        headers=_auth(emp_token),
        params={"specialization": "backend", "grade": "junior"},
    )
    items = r.json()["items"]
    assert items
    card = items[0]
    assert "ranking_score" not in card
    assert "match_reasons" in card
    assert isinstance(card["match_reasons"], list)


def test_search_result_has_no_contacts(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    _make_confirmed_candidate(cand_email, "backend", "junior")

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        "/api/v1/matching/candidates",
        headers=_auth(emp_token),
        params={"specialization": "backend"},
    )
    items = r.json()["items"]
    if items:
        dumped = items[0]
        assert "phone" not in dumped
        assert "email" not in dumped


def test_pagination(client):
    for _ in range(3):
        email = _email()
        _register_and_login(client, email, "candidate")
        _make_confirmed_candidate(email, "backend", "junior")

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        "/api/v1/matching/candidates",
        headers=_auth(emp_token),
        params={"page_size": 2, "page": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 2
    assert body["meta"]["page_size"] == 2


# --- Карточка ------------------------------------------------------------


def test_get_card(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    profile_id = _make_confirmed_candidate(cand_email, "backend", "junior")

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        f"/api/v1/matching/candidates/{profile_id}",
        headers=_auth(emp_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["profile_id"] == profile_id
    assert body["specialization_code"] == "backend"


def test_get_missing_card_returns_404(client):
    emp_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        "/api/v1/matching/candidates/999999",
        headers=_auth(emp_token),
    )
    assert r.status_code == 404