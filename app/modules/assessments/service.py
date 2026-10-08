"""Бизнес-логика тестирования: старт попытки, ответы, подсчёт, категории."""
from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.assessments.instantiate import (
    instantiate_question,
    is_correct,
    public_view,
)
from app.modules.assessments.models import (
    AttemptStatus,
    CandidateCategory,
    Category,
    CategoryStatus,
    Grade,
    Question,
    Specialization,
    TestAnswer,
    TestAttempt,
)
from app.modules.candidates.models import CandidateProfile


# --- Правила тестирования --------------------------------------------------

QUESTIONS_PER_ATTEMPT = 10
PASS_THRESHOLD = 0.70        # >= 70% — грейд подтверждён
RETRY_LOWER_THRESHOLD = 0.40  # 40–69% — предложить грейд ниже


class AssessmentError(Exception):
    """Базовая ошибка модуля assessments."""


class ProfileNotFound(AssessmentError):
    """Профиль кандидата не найден."""


class SpecializationNotFound(AssessmentError):
    """Специализация не найдена."""


class GradeNotFound(AssessmentError):
    """Грейд не найден."""


class NotEnoughQuestions(AssessmentError):
    """В пуле недостаточно вопросов для составления попытки."""


class AttemptNotFound(AssessmentError):
    """Попытка не найдена."""


class AttemptAlreadyCompleted(AssessmentError):
    """Попытка уже завершена."""


class ActiveAttemptExists(AssessmentError):
    """Уже есть активная попытка по этой категории."""

class AnswerNotFound(AssessmentError):
    """Ответ не найден."""


# --- Вспомогательные -------------------------------------------------------


def _get_profile(session: Session, user_id: int) -> CandidateProfile:
    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    )
    if profile is None:
        raise ProfileNotFound()
    return profile


def _get_specialization(session: Session, code: str) -> Specialization:
    spec = session.scalar(select(Specialization).where(Specialization.code == code))
    if spec is None:
        raise SpecializationNotFound(code)
    return spec


def _get_grade(session: Session, code: str) -> Grade:
    grade = session.scalar(select(Grade).where(Grade.code == code))
    if grade is None:
        raise GradeNotFound(code)
    return grade


# --- Старт попытки ---------------------------------------------------------


def start_attempt(
    session: Session,
    *,
    user_id: int,
    specialization_code: str,
    grade_code: str,
) -> TestAttempt:
    """Стартует новую попытку тестирования.

    Если у кандидата уже есть незавершённая попытка по этой специализации
    и грейду — возвращает её же, чтобы нельзя было пересоздавать попытку
    и получать новые вопросы.
    """
    profile = _get_profile(session, user_id)
    spec = _get_specialization(session, specialization_code)
    grade = _get_grade(session, grade_code)

    # 1. Проверяем, есть ли активная попытка
    existing = session.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.candidate_profile_id == profile.id,
            TestAttempt.specialization_id == spec.id,
            TestAttempt.target_grade_id == grade.id,
            TestAttempt.status == AttemptStatus.IN_PROGRESS,
        )
        .options(selectinload(TestAttempt.answers))
    )
    if existing is not None:
        return existing

    # 2. Выбираем пул вопросов по категории
    pool = list(
        session.scalars(
            select(Question).where(
                Question.specialization_id == spec.id,
                Question.grade_id == grade.id,
                Question.is_active.is_(True),
            )
        )
    )
    if len(pool) < QUESTIONS_PER_ATTEMPT:
        raise NotEnoughQuestions(
            f"В категории {spec.code}/{grade.code} только {len(pool)} вопросов, "
            f"нужно минимум {QUESTIONS_PER_ATTEMPT}"
        )

    # 3. Случайная выборка без повторов
    rng = random.Random()
    chosen = rng.sample(pool, QUESTIONS_PER_ATTEMPT)

    # 4. Создаём попытку
    attempt = TestAttempt(
        candidate_profile_id=profile.id,
        specialization_id=spec.id,
        declared_grade_id=grade.id,
        target_grade_id=grade.id,
        status=AttemptStatus.IN_PROGRESS,
    )
    session.add(attempt)
    session.flush()  # получаем attempt.id

    # 5. Инстанцируем каждый вопрос и сохраняем снапшот
    for question in chosen:
        snapshot = instantiate_question(question, rng)
        session.add(
            TestAnswer(
                test_attempt_id=attempt.id,
                question_id=question.id,
                question_snapshot=snapshot,
                answer=None,
                is_correct=None,
                answered_at=None,
            )
        )

    session.commit()
    return get_attempt(session, attempt_id=attempt.id, user_id=user_id)


def get_attempt(session: Session, *, attempt_id: int, user_id: int) -> TestAttempt:
    """Возвращает попытку с ответами. Проверяет принадлежность пользователю."""
    profile = _get_profile(session, user_id)
    attempt = session.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.id == attempt_id,
            TestAttempt.candidate_profile_id == profile.id,
        )
        .options(selectinload(TestAttempt.answers))
    )
    if attempt is None:
        raise AttemptNotFound()
    return attempt


def attempt_public_state(attempt: TestAttempt) -> dict[str, Any]:
    """Собирает публичное состояние попытки для отдачи клиенту.

    Правильные ответы не включаются. Правильность ранее данных ответов
    показывается только в завершённой попытке.
    """
    finished = attempt.status == AttemptStatus.COMPLETED
    answers = sorted(attempt.answers, key=lambda a: a.id)
    items = []
    for answer in answers:
        snap = answer.question_snapshot or {}
        public = public_view(snap)
        item = {
            "answer_id": answer.id,
            "question": public,
            "given": answer.answer,
            "answered": answer.answered_at is not None,
        }
        if finished:
            item["is_correct"] = answer.is_correct
        items.append(item)
    answered_count = sum(1 for a in answers if a.answered_at is not None)
    return {
        "attempt_id": attempt.id,
        "status": attempt.status.value,
        "score": attempt.score,
        "passed": attempt.passed,
        "started_at": attempt.started_at,
        "finished_at": attempt.finished_at,
        "total_questions": len(items),
        "answered_count": answered_count,
        "questions": items,
    }
# --- Ответы на вопросы ----------------------------------------------------


def submit_answer(
    session: Session,
    *,
    user_id: int,
    attempt_id: int,
    answer_id: int,
    answer_payload: dict[str, Any],
) -> TestAnswer:
    """Сохраняет ответ кандидата и сразу проверяет его правильность.

    Проверка происходит здесь, потому что правильный ответ лежит в снапшоте
    вопроса. Наружу `is_correct` не отдаётся, пока попытка не завершена.
    """
    profile = _get_profile(session, user_id)
    answer = session.scalar(
        select(TestAnswer)
        .join(TestAttempt, TestAttempt.id == TestAnswer.test_attempt_id)
        .where(
            TestAnswer.id == answer_id,
            TestAnswer.test_attempt_id == attempt_id,
            TestAttempt.candidate_profile_id == profile.id,
        )
    )
    if answer is None:
        raise AttemptNotFound()

    attempt = session.get(TestAttempt, attempt_id)
    if attempt is None or attempt.status != AttemptStatus.IN_PROGRESS:
        raise AttemptAlreadyCompleted()

    snapshot = answer.question_snapshot or {}
    answer.answer = answer_payload
    answer.is_correct = is_correct(snapshot, answer_payload)
    answer.answered_at = datetime.now(UTC)

    session.commit()
    session.refresh(answer)
    return answer