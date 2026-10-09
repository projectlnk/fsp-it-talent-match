"""Бизнес-логика тестирования: старт попытки, ответы, подсчёт, категории."""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update, func
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
    GradeChangeCooldown,
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
GRADE_CHANGE_COOLDOWN_DAYS = 60
MAX_FAILED_ATTEMPTS_PER_GRADE = 3
GRADE_RETRY_BLOCK_DAYS = 30
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

class InvalidAnswer(AssessmentError):
    """Ответ не соответствует типу вопроса или предложенным вариантам."""

class AnswerNotFound(AssessmentError):
    """Ответ не найден."""

class AttemptNotFinished(AssessmentError):
    """Попытка ещё не завершена."""

class AttemptBlocked(AssessmentError):
    """Попытка заблокирована правилами (кулдаун или лимит попыток)."""


# --- Вспомогательные -------------------------------------------------------


def _get_profile(session: Session, user_id: int, *, lock: bool = False) -> CandidateProfile:
    query = select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    profile = session.scalar(query.with_for_update() if lock else query)
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
    profile = _get_profile(session, user_id, lock=True)
    spec = _get_specialization(session, specialization_code)
    grade = _get_grade(session, grade_code)

    # 0. Проверяем кулдаун и лимиты
    check_can_start_attempt(
        session,
        user_id=user_id,
        specialization_code=specialization_code,
        grade_code=grade_code,
    )

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
    profile = _get_profile(session, user_id, lock=True)
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
    options = snapshot.get("options", [])
    if snapshot.get("type", "single_choice") == "multiple_choice":
        values = answer_payload.get("values")
        valid = (set(answer_payload) == {"values"} and isinstance(values, list)
                 and all(isinstance(value, str) and value in options for value in values)
                 and len(values) == len(set(values)))
    elif snapshot.get("type", "single_choice") == "single_choice":
        valid = set(answer_payload) == {"value"} and answer_payload.get("value") in options
    else:
        valid = set(answer_payload) == {"value"} and isinstance(answer_payload.get("value"), str)
    if not valid:
        raise InvalidAnswer("Выберите ответ из предложенных вариантов")
    answer.answer = answer_payload
    answer.is_correct = is_correct(snapshot, answer_payload)
    answer.answered_at = datetime.now(UTC)

    session.commit()
    session.refresh(answer)
    return answer

# --- Финиш попытки и подсчёт ----------------------------------------------


def _weighted_score(answers: list[TestAnswer]) -> float:
    """Взвешенный счёт: вес правильного ответа = difficulty вопроса.

    Возвращает долю от 0.0 до 1.0. Ответы без is_correct (не отвечено)
    считаются неправильными.
    """
    total_weight = 0
    correct_weight = 0
    for answer in answers:
        snap = answer.question_snapshot or {}
        weight = max(1, int(snap.get("difficulty", 1)))
        total_weight += weight
        if answer.is_correct:
            correct_weight += weight
    if total_weight == 0:
        return 0.0
    return correct_weight / total_weight


def finish_attempt(
    session: Session,
    *,
    user_id: int,
    attempt_id: int,
) -> TestAttempt:
    """Завершает попытку, считает взвешенный счёт, присваивает категорию.

    Возвращает обновлённую попытку.
    """
    profile = _get_profile(session, user_id, lock=True)
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
    if attempt.status == AttemptStatus.COMPLETED:
        raise AttemptAlreadyCompleted()
    if attempt.status == AttemptStatus.ABANDONED:
        raise AttemptAlreadyCompleted()

    ratio = _weighted_score(list(attempt.answers))
    attempt.score = int(round(ratio * 100))
    attempt.passed = ratio >= PASS_THRESHOLD
    attempt.status = AttemptStatus.COMPLETED
    attempt.finished_at = datetime.now(UTC)

    _apply_category(
        session,
        candidate_profile_id=profile.id,
        specialization_id=attempt.specialization_id,
        grade_id=attempt.target_grade_id,
        passed=attempt.passed,
        confirmed_at=attempt.finished_at if attempt.passed else None,
        test_score=attempt.score,   # ← добавили
    )

    if attempt.passed:
        _record_grade_change(
            session,
            candidate_profile_id=profile.id,
            when=attempt.finished_at,
        )

    session.commit()
    return get_attempt(session, attempt_id=attempt.id, user_id=user_id)


def _apply_category(
    session: Session,
    *,
    candidate_profile_id: int,
    specialization_id: int,
    grade_id: int,
    passed: bool,
    confirmed_at: datetime | None,
    test_score: int | None = None,
) -> CandidateCategory:
    """Создаёт новую запись CandidateCategory и снимает флаг is_current
    с предыдущей.

    История сохраняется: старые записи остаются в БД.
    """
    # Снимаем is_current со всех предыдущих записей этого кандидата
    session.execute(
        update(CandidateCategory)
        .where(
            CandidateCategory.candidate_profile_id == candidate_profile_id,
            CandidateCategory.is_current.is_(True),
        )
        .values(is_current=False)
    )

    category = session.scalar(
        select(Category).where(
            Category.specialization_id == specialization_id,
            Category.grade_id == grade_id,
        )
    )
    if category is None:
        raise SpecializationNotFound(
            f"Категория для specialization_id={specialization_id}, "
            f"grade_id={grade_id} не найдена"
        )

    record = CandidateCategory(
        candidate_profile_id=candidate_profile_id,
        category_id=category.id,
        status=CategoryStatus.CONFIRMED if passed else CategoryStatus.NOT_CONFIRMED,
        is_current=True,
        test_score=test_score,
        confirmed_at=confirmed_at,
    )
    session.add(record)
    session.flush()
    return record


def current_category(
    session: Session,
    *,
    user_id: int,
) -> CandidateCategory | None:
    """Возвращает текущую категорию кандидата, если есть."""
    profile = _get_profile(session, user_id)
    return session.scalar(
        select(CandidateCategory)
        .where(
            CandidateCategory.candidate_profile_id == profile.id,
            CandidateCategory.is_current.is_(True),
        )
        .order_by(CandidateCategory.id.desc())
    )

# --- Кулдаун и лимиты попыток ---------------------------------------------


def _get_cooldown(session: Session, candidate_profile_id: int) -> GradeChangeCooldown | None:
    return session.scalar(
        select(GradeChangeCooldown).where(
            GradeChangeCooldown.candidate_profile_id == candidate_profile_id
        )
    )


def _failed_attempts_count(
    session: Session, *, profile_id: int, spec_id: int, grade_id: int
) -> int:
    count = session.scalar(
        select(func.count())
        .select_from(TestAttempt)
        .where(
            TestAttempt.candidate_profile_id == profile_id,
            TestAttempt.specialization_id == spec_id,
            TestAttempt.target_grade_id == grade_id,
            TestAttempt.status == AttemptStatus.COMPLETED,
            TestAttempt.passed.is_(False),
        )
    )
    return int(count or 0)


def _last_failed_attempt(
    session: Session, *, profile_id: int, spec_id: int, grade_id: int
) -> TestAttempt | None:
    return session.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.candidate_profile_id == profile_id,
            TestAttempt.specialization_id == spec_id,
            TestAttempt.target_grade_id == grade_id,
            TestAttempt.status == AttemptStatus.COMPLETED,
            TestAttempt.passed.is_(False),
        )
        .order_by(TestAttempt.finished_at.desc())
        .limit(1)
    )


def check_can_start_attempt(
    session: Session,
    *,
    user_id: int,
    specialization_code: str,
    grade_code: str,
) -> None:
    """Проверяет кулдауны и лимиты.

    Поднимает AttemptBlocked, если попытку начать нельзя.
    """
    profile = _get_profile(session, user_id)
    spec = _get_specialization(session, specialization_code)
    target_grade = _get_grade(session, grade_code)
    now = datetime.now(UTC)

    # 1. Общий кулдаун на смену грейда
    cooldown = _get_cooldown(session, profile.id)
    if cooldown is not None and now < cooldown.next_allowed_at:
        current = session.scalar(select(CandidateCategory).where(
            CandidateCategory.candidate_profile_id == profile.id,
            CandidateCategory.status == CategoryStatus.CONFIRMED,
        ).order_by(CandidateCategory.confirmed_at.desc().nullslast(), CandidateCategory.id.desc()))
        if current is not None:
            current_cat = session.get(Category, current.category_id)
            if current_cat is not None and current_cat.grade_id != target_grade.id:
                days_left = (cooldown.next_allowed_at - now).days
                raise AttemptBlocked(
                    f"Смена грейда доступна раз в {GRADE_CHANGE_COOLDOWN_DAYS} дней. "
                    f"Осталось {days_left} дн."
                )

    # 2. Лимит провалов на этот грейд
    failed = _failed_attempts_count(
        session, profile_id=profile.id, spec_id=spec.id, grade_id=target_grade.id
    )
    if failed >= MAX_FAILED_ATTEMPTS_PER_GRADE:
        last = _last_failed_attempt(
            session, profile_id=profile.id, spec_id=spec.id, grade_id=target_grade.id
        )
        if last is not None and last.finished_at is not None:
            block_until = last.finished_at + timedelta(days=GRADE_RETRY_BLOCK_DAYS)
            if now < block_until:
                days_left = (block_until - now).days
                raise AttemptBlocked(
                    f"Превышен лимит {MAX_FAILED_ATTEMPTS_PER_GRADE} попыток "
                    f"на грейд. Повтор доступен через {days_left} дн."
                )


def cooldown_status(session: Session, *, user_id: int) -> dict[str, Any]:
    """Возвращает состояние кулдауна для UI."""
    profile = _get_profile(session, user_id)
    cooldown = _get_cooldown(session, profile.id)
    now = datetime.now(UTC)
    if cooldown is None or cooldown.next_allowed_at <= now:
        return {
            "active": False,
            "next_allowed_at": cooldown.next_allowed_at if cooldown else None,
            "days_left": 0,
        }
    return {
        "active": True,
        "next_allowed_at": cooldown.next_allowed_at,
        "days_left": (cooldown.next_allowed_at - now).days,
    }


def _record_grade_change(
    session: Session, *, candidate_profile_id: int, when: datetime
) -> None:
    """Обновляет или создаёт запись кулдауна после успешной смены грейда."""
    cooldown = _get_cooldown(session, candidate_profile_id)
    next_allowed = when + timedelta(days=GRADE_CHANGE_COOLDOWN_DAYS)
    if cooldown is None:
        session.add(
            GradeChangeCooldown(
                candidate_profile_id=candidate_profile_id,
                last_change_at=when,
                next_allowed_at=next_allowed,
            )
        )
    else:
        cooldown.last_change_at = when
        cooldown.next_allowed_at = next_allowed