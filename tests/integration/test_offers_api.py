"""Интеграционные тесты JSON API приглашений."""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.service import update_profile

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
PREFIX = "offers-api-"


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


def _get_candidate_profile_id(email: str) -> int:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        profile = session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user.id)
        )
        return profile.id


def _set_candidate_phone(email: str, phone: str) -> None:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        update_profile(session, user_id=user.id, changes={"phone": phone})


def _offer_payload(profile_id: int) -> dict:
    return {
        "candidate_profile_id": profile_id,
        "title": "Backend Developer",
        "description": "Приходите",
        "salary_from": 200000,
        "salary_to": 300000,
        "salary_gross": True,
        "contact_method": "Telegram: @hr",
    }


# --- Доступ --------------------------------------------------------------


def test_employer_endpoint_requires_auth(client):
    r = client.get("/api/v1/employers/offers")
    assert r.status_code == 401


def test_candidate_endpoint_requires_auth(client):
    r = client.get("/api/v1/candidates/me/offers")
    assert r.status_code == 401


def test_candidate_cannot_create_offer(client):
    token = _register_and_login(client, _email(), "candidate")
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(token),
        json=_offer_payload(1),
    )
    assert r.status_code == 403


# --- Жизненный цикл -------------------------------------------------------


def test_full_offer_flow(client):
    """Сквозной сценарий: создание → просмотр → принятие → контакты."""
    cand_email = _email()
    cand_token = _register_and_login(client, cand_email, "candidate")
    _set_candidate_phone(cand_email, "+7 999 111-22-33")
    profile_id = _get_candidate_profile_id(cand_email)

    emp_token = _register_and_login(client, _email(), "employer")

    # 1. Создание
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=_offer_payload(profile_id),
    )
    assert r.status_code == 201, r.text
    offer = r.json()
    assert offer["status"] == "sent"
    assert offer["contacts"] is None
    offer_id = offer["id"]

    # 2. Кандидат видит приглашение
    r = client.get("/api/v1/candidates/me/offers", headers=_auth(cand_token))
    assert r.status_code == 200
    assert any(o["id"] == offer_id for o in r.json())

    # 3. Кандидат помечает просмотренным
    r = client.post(
        f"/api/v1/candidates/me/offers/{offer_id}/view",
        headers=_auth(cand_token),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "viewed"

    # 4. Работодатель до принятия контактов не видит
    r = client.get(
        f"/api/v1/employers/offers/{offer_id}",
        headers=_auth(emp_token),
    )
    assert r.json()["contacts"] is None

    # 5. Кандидат принимает
    r = client.post(
        f"/api/v1/candidates/me/offers/{offer_id}/respond",
        headers=_auth(cand_token),
        json={"status": "accepted"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    # 6. Работодатель видит контакты
    r = client.get(
        f"/api/v1/employers/offers/{offer_id}",
        headers=_auth(emp_token),
    )
    contacts = r.json()["contacts"]
    assert contacts is not None
    assert contacts["phone"] == "+7 999 111-22-33"
    assert contacts["email"] == cand_email


def test_reject_does_not_reveal_contacts(client):
    cand_email = _email()
    cand_token = _register_and_login(client, cand_email, "candidate")
    profile_id = _get_candidate_profile_id(cand_email)

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=_offer_payload(profile_id),
    )
    offer_id = r.json()["id"]

    client.post(
        f"/api/v1/candidates/me/offers/{offer_id}/respond",
        headers=_auth(cand_token),
        json={"status": "rejected"},
    )

    r = client.get(
        f"/api/v1/employers/offers/{offer_id}",
        headers=_auth(emp_token),
    )
    body = r.json()
    assert body["status"] == "rejected"
    assert body["contacts"] is None


def test_cannot_respond_twice(client):
    cand_email = _email()
    cand_token = _register_and_login(client, cand_email, "candidate")
    profile_id = _get_candidate_profile_id(cand_email)

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=_offer_payload(profile_id),
    )
    offer_id = r.json()["id"]

    client.post(
        f"/api/v1/candidates/me/offers/{offer_id}/respond",
        headers=_auth(cand_token),
        json={"status": "accepted"},
    )
    r = client.post(
        f"/api/v1/candidates/me/offers/{offer_id}/respond",
        headers=_auth(cand_token),
        json={"status": "rejected"},
    )
    assert r.status_code == 409


# --- Изоляция ------------------------------------------------------------


def test_employer_cannot_see_foreign_offer(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    profile_id = _get_candidate_profile_id(cand_email)

    emp1_token = _register_and_login(client, _email(), "employer")
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp1_token),
        json=_offer_payload(profile_id),
    )
    offer_id = r.json()["id"]

    emp2_token = _register_and_login(client, _email(), "employer")
    r = client.get(
        f"/api/v1/employers/offers/{offer_id}",
        headers=_auth(emp2_token),
    )
    assert r.status_code == 404


def test_candidate_cannot_see_foreign_offer(client):
    # Кандидат 1 получает приглашение
    cand1_email = _email()
    _register_and_login(client, cand1_email, "candidate")
    profile1_id = _get_candidate_profile_id(cand1_email)

    emp_token = _register_and_login(client, _email(), "employer")
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=_offer_payload(profile1_id),
    )
    offer_id = r.json()["id"]

    # Кандидат 2 пытается посмотреть чужое приглашение
    cand2_token = _register_and_login(client, _email(), "candidate")
    r = client.get(
        f"/api/v1/candidates/me/offers/{offer_id}",
        headers=_auth(cand2_token),
    )
    assert r.status_code == 404


# --- Списки --------------------------------------------------------------


def test_employer_list(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    profile_id = _get_candidate_profile_id(cand_email)

    emp_token = _register_and_login(client, _email(), "employer")
    client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=_offer_payload(profile_id),
    )

    r = client.get("/api/v1/employers/offers", headers=_auth(emp_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_candidate_list(client):
    cand_email = _email()
    cand_token = _register_and_login(client, cand_email, "candidate")
    profile_id = _get_candidate_profile_id(cand_email)

    emp1_token = _register_and_login(client, _email(), "employer")
    emp2_token = _register_and_login(client, _email(), "employer")
    client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp1_token),
        json=_offer_payload(profile_id),
    )
    client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp2_token),
        json=_offer_payload(profile_id),
    )

    r = client.get("/api/v1/candidates/me/offers", headers=_auth(cand_token))
    assert r.status_code == 200
    assert len(r.json()) >= 2


# --- Валидация -----------------------------------------------------------


def test_create_offer_with_invalid_salary_range(client):
    cand_email = _email()
    _register_and_login(client, cand_email, "candidate")
    profile_id = _get_candidate_profile_id(cand_email)

    emp_token = _register_and_login(client, _email(), "employer")
    payload = _offer_payload(profile_id)
    payload["salary_from"] = 300000
    payload["salary_to"] = 100000

    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=payload,
    )
    assert r.status_code == 422


def test_create_offer_for_missing_candidate(client):
    emp_token = _register_and_login(client, _email(), "employer")
    r = client.post(
        "/api/v1/employers/offers",
        headers=_auth(emp_token),
        json=_offer_payload(999_999),
    )
    assert r.status_code == 404