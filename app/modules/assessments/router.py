"""JSON API тестирования.

Все ручки защищены ролью candidate. Работают от имени текущего пользователя.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_session
from app.modules.assessments import service
from app.modules.assessments.models import (
    CandidateCategory,
    Category,
    Grade,
    Specialization,
    TestAttempt,
)
from app.modules.assessments.schemas import (
    AttemptStateResponse,
    AttemptSummary,
    CategoryRead,
    CooldownRead,
    GradeRead,
    SpecializationRead,
    StartAttemptRequest,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

router = APIRouter(prefix="/assessments", tags=["assessments"])

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


def _handle(exc: service.AssessmentError) -> HTTPException:
    if isinstance(
        exc,
        (
            service.ProfileNotFound,
            service.SpecializationNotFound,
            service.GradeNotFound,
            service.AttemptNotFound,
            service.AnswerNotFound,
        ),
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc) or "Не найдено")
    if isinstance(
        exc,
        (service.AttemptAlreadyCompleted, service.ActiveAttemptExists),
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or "Конфликт")
    if isinstance(exc, service.AttemptBlocked):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if isinstance(exc, service.NotEnoughQuestions):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --- Справочники ----------------------------------------------------------


@router.get("/specializations", response_model=list[SpecializationRead], summary="Специализации")
def list_specializations(session: Session = Depends(get_session)):
    return list(session.scalars(select(Specialization).order_by(Specialization.id)))


@router.get("/grades", response_model=list[GradeRead], summary="Грейды")
def list_grades(session: Session = Depends(get_session)):
    return list(session.scalars(select(Grade).order_by(Grade.order)))


# --- Текущее состояние ----------------------------------------------------


@router.get("/cooldown", response_model=CooldownRead, summary="Состояние кулдауна")
def get_cooldown(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.cooldown_status(session, user_id=user.id)
    except service.AssessmentError as exc:
        raise _handle(exc) from exc


@router.get("/current", response_model=CategoryRead | None, summary="Текущая категория")
def get_current_category(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        record = service.current_category(session, user_id=user.id)
    except service.AssessmentError as exc:
        raise _handle(exc) from exc
    if record is None:
        return None

    category = session.get(Category, record.category_id)
    if category is None:
        return None
    spec = session.get(Specialization, category.specialization_id)
    grade = session.get(Grade, category.grade_id)
    return CategoryRead(
        id=record.id,
        status=record.status.value,
        is_current=record.is_current,
        confirmed_at=record.confirmed_at,
        specialization=SpecializationRead.model_validate(spec),
        grade=GradeRead.model_validate(grade),
    )


# --- Попытки --------------------------------------------------------------


def _attempt_summary(session: Session, attempt: TestAttempt) -> AttemptSummary:
    spec = session.get(Specialization, attempt.specialization_id)
    grade = session.get(Grade, attempt.target_grade_id)
    return AttemptSummary(
        attempt_id=attempt.id,
        status=attempt.status.value,
        score=attempt.score,
        passed=attempt.passed,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        specialization=SpecializationRead.model_validate(spec),
        grade=GradeRead.model_validate(grade),
    )


@router.post(
    "/attempts",
    response_model=AttemptSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Старт попытки",
)
def start_attempt(
    payload: StartAttemptRequest,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        attempt = service.start_attempt(
            session,
            user_id=user.id,
            specialization_code=payload.specialization,
            grade_code=payload.grade,
        )
    except service.AssessmentError as exc:
        raise _handle(exc) from exc
    return _attempt_summary(session, attempt)


@router.get(
    "/attempts",
    response_model=list[AttemptSummary],
    summary="История попыток",
)
def list_attempts(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        profile = service._get_profile(session, user.id)
    except service.AssessmentError as exc:
        raise _handle(exc) from exc
    attempts = list(
        session.scalars(
            select(TestAttempt)
            .where(TestAttempt.candidate_profile_id == profile.id)
            .order_by(TestAttempt.id.desc())
        )
    )
    return [_attempt_summary(session, a) for a in attempts]


@router.get(
    "/attempts/{attempt_id}",
    response_model=AttemptStateResponse,
    summary="Состояние попытки",
)
def get_attempt(
    attempt_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        attempt = service.get_attempt(session, attempt_id=attempt_id, user_id=user.id)
    except service.AssessmentError as exc:
        raise _handle(exc) from exc
    return service.attempt_public_state(attempt)


@router.post(
    "/attempts/{attempt_id}/answers/{answer_id}",
    response_model=SubmitAnswerResponse,
    summary="Ответ на вопрос",
)
def submit_answer(
    attempt_id: int,
    answer_id: int,
    payload: SubmitAnswerRequest,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    answer_payload: dict = {}
    if payload.value is not None:
        answer_payload["value"] = payload.value
    if payload.values is not None:
        answer_payload["values"] = payload.values

    try:
        answer = service.submit_answer(
            session,
            user_id=user.id,
            attempt_id=attempt_id,
            answer_id=answer_id,
            answer_payload=answer_payload,
        )
    except service.AssessmentError as exc:
        raise _handle(exc) from exc
    return SubmitAnswerResponse(answer_id=answer.id, answered=True)


@router.post(
    "/attempts/{attempt_id}/finish",
    response_model=AttemptStateResponse,
    summary="Завершить попытку",
)
def finish_attempt(
    attempt_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        attempt = service.finish_attempt(session, user_id=user.id, attempt_id=attempt_id)
    except service.AssessmentError as exc:
        raise _handle(exc) from exc
    return service.attempt_public_state(attempt)