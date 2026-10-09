"""Интеграционные тесты API тестирования.

Покрывают: справочники, старт попытки, ответы, финиш, категоризацию,
кулдаун, лимит провалов, ролевой доступ.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.assessments.models import (
    CandidateCategory,
    GradeChangeCooldown,
    TestAnswer,
    TestAttempt,
)
from app.modules.auth.models import User

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
PREFIX = "assess-test-"


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
        json={"email": email, "password": "test1234", "role": role, "full_name": "Test"},
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "test1234"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _start_attempt(client, token, spec="backend", grade="junior") -> dict:
    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": spec, "grade": grade},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _attempt_state(client, token, attempt_id) -> dict:
    r = client.get(
        f"/api/v1/assessments/attempts/{attempt_id}",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _answer_all(client, token, attempt_id, correct: bool) -> None:
    """Отвечает на все вопросы попытки. correct=True — правильно, False — нет."""
    state = _attempt_state(client, token, attempt_id)
    with SessionLocal() as session:
        for q in state["questions"]:
            answer = session.get(TestAnswer, q["answer_id"])
            snap = answer.question_snapshot or {}
            assert snap["correct"] in snap["options"]
            payload = {"value": snap["correct"] if correct else next(value for value in snap["options"] if value != snap["correct"])}
            r = client.post(
                f"/api/v1/assessments/attempts/{attempt_id}/answers/{q['answer_id']}",
                headers=_auth(token),
                json=payload,
            )
            assert r.status_code == 200, r.text


# --- Справочники ---------------------------------------------------------


def test_specializations_list(client):
    token = _register_and_login(client, _email())
    r = client.get("/api/v1/assessments/specializations", headers=_auth(token))
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()}
    assert {"backend", "frontend"} <= codes


def test_grades_list(client):
    token = _register_and_login(client, _email())
    r = client.get("/api/v1/assessments/grades", headers=_auth(token))
    assert r.status_code == 200
    codes = {g["code"] for g in r.json()}
    assert {"intern", "junior", "middle", "senior"} <= codes


# --- Доступ --------------------------------------------------------------


def test_specializations_are_public(client):
    """Справочники публичные — их можно показывать без авторизации."""
    r = client.get("/api/v1/assessments/specializations")
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_protected_endpoint_requires_auth(client):
    """Защищённые ручки без токена — 401."""
    r = client.get("/api/v1/assessments/cooldown")
    assert r.status_code == 401

    r = client.get("/api/v1/assessments/current")
    assert r.status_code == 401

    r = client.post(
        "/api/v1/assessments/attempts",
        json={"specialization": "backend", "grade": "junior"},
    )
    assert r.status_code == 401


def test_employer_forbidden(client):
    token = _register_and_login(client, _email(), role="employer")
    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "backend", "grade": "junior"},
    )
    assert r.status_code == 403


# --- Старт попытки -------------------------------------------------------


def test_start_attempt(client):
    token = _register_and_login(client, _email())
    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "backend", "grade": "junior"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["specialization"]["code"] == "backend"
    assert body["grade"]["code"] == "junior"


def test_start_unknown_specialization(client):
    token = _register_and_login(client, _email())
    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "no-such-spec", "grade": "junior"},
    )
    assert r.status_code == 404


def test_start_unknown_grade(client):
    token = _register_and_login(client, _email())
    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "backend", "grade": "no-such-grade"},
    )
    assert r.status_code == 404


def test_second_start_returns_same_attempt(client):
    """Повторный старт той же категории возвращает существующую попытку."""
    token = _register_and_login(client, _email())
    first = _start_attempt(client, token)
    second = _start_attempt(client, token)
    assert first["attempt_id"] == second["attempt_id"]


# --- Состояние попытки ---------------------------------------------------


def test_attempt_state_has_10_questions(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    state = _attempt_state(client, token, attempt["attempt_id"])
    assert state["total_questions"] == 10
    assert state["answered_count"] == 0
    assert state["status"] == "in_progress"


def test_attempt_does_not_leak_correct_answers(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    state = _attempt_state(client, token, attempt["attempt_id"])
    for q in state["questions"]:
        assert "correct" not in q["question"]
        assert "is_correct" not in q
        assert q["answered"] is False


# --- Ответы --------------------------------------------------------------


def test_submit_correct_answer(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    state = _attempt_state(client, token, attempt["attempt_id"])

    with SessionLocal() as session:
        answer_id = state["questions"][0]["answer_id"]
        snap = session.get(TestAnswer, answer_id).question_snapshot or {}

    r = client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/answers/{answer_id}",
        headers=_auth(token),
        json={"value": snap["correct"]},
    )
    assert r.status_code == 200

    state = _attempt_state(client, token, attempt["attempt_id"])
    assert state["answered_count"] == 1


def test_cannot_answer_foreign_attempt(client):
    token1 = _register_and_login(client, _email())
    token2 = _register_and_login(client, _email())
    attempt = _start_attempt(client, token1)
    state = _attempt_state(client, token1, attempt["attempt_id"])
    answer_id = state["questions"][0]["answer_id"]

    r = client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/answers/{answer_id}",
        headers=_auth(token2),
        json={"value": "anything"},
    )
    assert r.status_code == 404


# --- Финиш и категоризация ----------------------------------------------


def test_finish_all_correct_confirms_grade(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=True)

    r = client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["score"] == 100
    assert body["passed"] is True

    # категория confirmed
    r = client.get("/api/v1/assessments/current", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert r.json()["is_current"] is True


def test_finish_all_wrong_not_confirmed(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=False)

    r = client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["passed"] is False

    r = client.get("/api/v1/assessments/current", headers=_auth(token))
    assert r.json()["status"] == "not_confirmed"


def test_cannot_finish_twice(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=True)
    client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )
    r = client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )
    assert r.status_code == 409


# --- Кулдаун -------------------------------------------------------------


def test_cooldown_active_after_success(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=True)
    client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )

    r = client.get("/api/v1/assessments/cooldown", headers=_auth(token))
    assert r.json()["active"] is True
    assert r.json()["days_left"] >= 59


def test_grade_change_blocked_by_cooldown(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=True)
    client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )

    # Попытка на другой грейд — блок
    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "backend", "grade": "middle"},
    )
    assert r.status_code == 429
    assert "Смена грейда" in r.json()["detail"]


def test_failed_attempt_does_not_trigger_cooldown(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=False)
    client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )

    r = client.get("/api/v1/assessments/cooldown", headers=_auth(token))
    assert r.json()["active"] is False


# --- Лимит провалов ------------------------------------------------------


def test_three_failures_block_next_attempt(client):
    token = _register_and_login(client, _email())
    for _ in range(3):
        attempt = _start_attempt(client, token)
        _answer_all(client, token, attempt["attempt_id"], correct=False)
        client.post(
            f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
            headers=_auth(token),
        )

    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "backend", "grade": "junior"},
    )
    assert r.status_code == 429
    assert "лимит" in r.json()["detail"].lower()


def test_lower_grade_allowed_after_block(client):
    """Уход ниже не блокируется лимитом провалов."""
    token = _register_and_login(client, _email())
    for _ in range(3):
        attempt = _start_attempt(client, token)
        _answer_all(client, token, attempt["attempt_id"], correct=False)
        client.post(
            f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
            headers=_auth(token),
        )

    r = client.post(
        "/api/v1/assessments/attempts",
        headers=_auth(token),
        json={"specialization": "backend", "grade": "intern"},
    )
    assert r.status_code == 201


# --- История -------------------------------------------------------------


def test_attempts_history(client):
    token = _register_and_login(client, _email())
    attempt = _start_attempt(client, token)
    _answer_all(client, token, attempt["attempt_id"], correct=True)
    client.post(
        f"/api/v1/assessments/attempts/{attempt['attempt_id']}/finish",
        headers=_auth(token),
    )

    r = client.get("/api/v1/assessments/attempts", headers=_auth(token))
    assert r.status_code == 200
    assert len(r.json()) >= 1