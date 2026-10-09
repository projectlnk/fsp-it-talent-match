"""Интеграционные тесты API привязки к ФСП ID.

Используют реальный mock mini-fsp-id по сети Compose.
"""
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
PREFIX = "fsp-test-"


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


def _register_and_login(client, email, role="candidate") -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "test1234",
            "role": role,
            "full_name": "Test",
        },
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "test1234"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _link(client, token, participant_id: str):
    return client.post(
        "/api/v1/candidates/me/fsp/link",
        headers=_auth(token),
        json={"participant_id": participant_id},
    )


# --- Доступ --------------------------------------------------------------


def test_requires_auth(client):
    r = client.get("/api/v1/candidates/me/fsp")
    assert r.status_code == 401


def test_employer_forbidden(client):
    token = _register_and_login(client, _email(), role="employer")
    r = client.get("/api/v1/candidates/me/fsp", headers=_auth(token))
    assert r.status_code == 403


# --- Состояние -----------------------------------------------------------


def test_initial_state_empty(client):
    token = _register_and_login(client, _email())
    r = client.get("/api/v1/candidates/me/fsp", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["link"] is None
    assert body["achievements"] == []


def test_available_participants(client):
    token = _register_and_login(client, _email())
    r = client.get("/api/v1/candidates/me/fsp/available", headers=_auth(token))
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert {"demo-1", "demo-2", "demo-3"} <= ids


# --- Привязка ------------------------------------------------------------


def test_link_demo1_imports_achievements(client):
    token = _register_and_login(client, _email())
    r = _link(client, token, "demo-1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["link"]["registry_participant_id"] == "demo-1"
    assert len(body["achievements"]) == 4
    assert all(a["is_demo"] is True for a in body["achievements"])
    # есть и командное, и личное достижение
    kinds = {a["is_team"] for a in body["achievements"]}
    assert kinds == {True, False}


def test_link_demo2_no_achievements(client):
    token = _register_and_login(client, _email())
    r = _link(client, token, "demo-2")
    assert r.status_code == 200
    body = r.json()
    assert body["link"]["registry_participant_id"] == "demo-2"
    assert body["achievements"] == []


def test_link_missing_participant_returns_404(client):
    token = _register_and_login(client, _email())
    r = _link(client, token, "no-such-participant")
    assert r.status_code == 404


def test_link_twice_is_idempotent(client):
    token = _register_and_login(client, _email())
    _link(client, token, "demo-1")
    r = _link(client, token, "demo-1")
    assert r.status_code == 200
    assert len(r.json()["achievements"]) == 4


def test_participant_cannot_be_linked_to_two_profiles(client):
    token1 = _register_and_login(client, _email())
    token2 = _register_and_login(client, _email())
    assert _link(client, token1, "demo-3").status_code == 200
    r = _link(client, token2, "demo-3")
    assert r.status_code == 409


def test_link_replaces_previous(client):
    """Привязка другого участника заменяет прежнюю связь."""
    token = _register_and_login(client, _email())
    _link(client, token, "demo-1")
    r = _link(client, token, "demo-2")
    assert r.status_code == 200
    body = r.json()
    assert body["link"]["registry_participant_id"] == "demo-2"
    assert body["achievements"] == []


# --- Отвязка -------------------------------------------------------------


def test_unlink(client):
    token = _register_and_login(client, _email())
    _link(client, token, "demo-1")

    r = client.delete("/api/v1/candidates/me/fsp/link", headers=_auth(token))
    assert r.status_code == 204

    r = client.get("/api/v1/candidates/me/fsp", headers=_auth(token))
    assert r.json()["link"] is None
    assert r.json()["achievements"] == []


def test_unlink_when_not_linked(client):
    """Отвязка без связи — не ошибка."""
    token = _register_and_login(client, _email())
    r = client.delete("/api/v1/candidates/me/fsp/link", headers=_auth(token))
    assert r.status_code == 204