"""HTML-страницы тестирования кандидата.

Прохождение пошаговое: одна страница — один вопрос. Ответ отправляется
формой POST + redirect, что защищает от показа всех вопросов сразу
через исходник страницы.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.assessments import service
from app.modules.assessments.models import (
    CandidateCategory,
    Category,
    Grade,
    Specialization,
    TestAttempt,
)
from app.modules.assessments.models import AttemptStatus
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.web.templates import templates

router = APIRouter(prefix="/assessments", tags=["assessments-web"], include_in_schema=False)

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


def _render(request: Request, user: User, template: str, context: dict, status_code: int = 200):
    base = {"user": user}
    base.update(context)
    return templates.TemplateResponse(
        request=request, name=template, context=base, status_code=status_code
    )


# --- Главная страница -----------------------------------------------------


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    profile = service._get_profile(session, user.id)

    # текущая категория
    current = service.current_category(session, user_id=user.id)
    current_data = None
    if current is not None:
        cat = session.get(Category, current.category_id)
        if cat is not None:
            current_data = {
                "status": current.status.value,
                "confirmed_at": current.confirmed_at,
                "specialization": session.get(Specialization, cat.specialization_id),
                "grade": session.get(Grade, cat.grade_id),
            }

    cooldown = service.cooldown_status(session, user_id=user.id)

    attempts = list(
        session.scalars(
            select(TestAttempt)
            .where(TestAttempt.candidate_profile_id == profile.id)
            .order_by(TestAttempt.id.desc())
            .limit(20)
        )
    )
    attempts_data = []
    for a in attempts:
        attempts_data.append(
            {
                "id": a.id,
                "status": a.status.value,
                "score": a.score,
                "passed": a.passed,
                "started_at": a.started_at,
                "finished_at": a.finished_at,
                "specialization": session.get(Specialization, a.specialization_id),
                "grade": session.get(Grade, a.target_grade_id),
            }
        )

    # есть ли активная попытка
    active = session.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.candidate_profile_id == profile.id,
            TestAttempt.status == AttemptStatus.IN_PROGRESS,
        )
        .order_by(TestAttempt.id.desc())
        .limit(1)
    )

    return _render(
        request,
        user,
        "assessments/index.html",
        {
            "current": current_data,
            "cooldown": cooldown,
            "attempts": attempts_data,
            "active_attempt_id": active.id if active else None,
        },
    )


# --- Старт попытки --------------------------------------------------------


@router.get("/start", response_class=HTMLResponse)
def start_form(
    request: Request,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    specializations = list(session.scalars(select(Specialization).order_by(Specialization.id)))
    grades = list(session.scalars(select(Grade).order_by(Grade.order)))
    return _render(
        request,
        user,
        "assessments/start.html",
        {
            "specializations": specializations,
            "grades": grades,
            "error": None,
        },
    )


@router.post("/start", response_class=HTMLResponse)
def start_submit(
    request: Request,
    specialization: str = Form(...),
    grade: str = Form(...),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        attempt = service.start_attempt(
            session,
            user_id=user.id,
            specialization_code=specialization,
            grade_code=grade,
        )
    except service.AttemptBlocked as exc:
        specializations = list(session.scalars(select(Specialization).order_by(Specialization.id)))
        grades = list(session.scalars(select(Grade).order_by(Grade.order)))
        return _render(
            request,
            user,
            "assessments/start.html",
            {
                "specializations": specializations,
                "grades": grades,
                "error": str(exc),
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    except service.AssessmentError as exc:
        specializations = list(session.scalars(select(Specialization).order_by(Specialization.id)))
        grades = list(session.scalars(select(Grade).order_by(Grade.order)))
        return _render(
            request,
            user,
            "assessments/start.html",
            {
                "specializations": specializations,
                "grades": grades,
                "error": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse(
        f"/assessments/attempt/{attempt.id}", status_code=status.HTTP_303_SEE_OTHER
    )


# --- Прохождение ----------------------------------------------------------


def _attempt_context(session: Session, attempt: TestAttempt, user: User) -> dict:
    """Собирает контекст для страницы прохождения: следующий вопрос или финиш."""
    answers = sorted(attempt.answers, key=lambda a: a.id)
    answered = [a for a in answers if a.answered_at is not None]
    unanswered = [a for a in answers if a.answered_at is None]

    spec = session.get(Specialization, attempt.specialization_id)
    grade = session.get(Grade, attempt.target_grade_id)

    if not unanswered:
        return {
            "attempt": attempt,
            "spec": spec,
            "grade": grade,
            "current": None,
            "answered_count": len(answered),
            "total": len(answers),
            "all_answered": True,
        }

    answer = unanswered[0]
    snap = answer.question_snapshot or {}
    return {
        "attempt": attempt,
        "spec": spec,
        "grade": grade,
        "current": {
            "answer_id": answer.id,
            "text": snap.get("text"),
            "options": snap.get("options", []),
            "type": snap.get("type", "single_choice"),
        },
        "answered_count": len(answered),
        "total": len(answers),
        "all_answered": False,
    }


@router.get("/attempt/{attempt_id}", response_class=HTMLResponse)
def attempt_page(
    request: Request,
    attempt_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        attempt = service.get_attempt(session, attempt_id=attempt_id, user_id=user.id)
    except service.AssessmentError:
        return RedirectResponse("/assessments", status_code=status.HTTP_303_SEE_OTHER)

    if attempt.status == AttemptStatus.COMPLETED:
        return RedirectResponse(
            f"/assessments/attempt/{attempt.id}/result",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    context = _attempt_context(session, attempt, user)
    if context["all_answered"]:
        return RedirectResponse(
            f"/assessments/attempt/{attempt.id}/finish",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return _render(request, user, "assessments/attempt.html", context)


@router.post("/attempt/{attempt_id}/answer")
def attempt_answer(
    attempt_id: int,
    answer_id: int = Form(...),
    value: str = Form(""),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.submit_answer(
            session,
            user_id=user.id,
            attempt_id=attempt_id,
            answer_id=answer_id,
            answer_payload={"value": value} if value else {},
        )
    except service.AssessmentError:
        pass  # редирект покажет актуальное состояние
    return RedirectResponse(
        f"/assessments/attempt/{attempt_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/attempt/{attempt_id}/finish", response_class=HTMLResponse)
def attempt_finish_page(
    request: Request,
    attempt_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.get_attempt(session, attempt_id=attempt_id, user_id=user.id)
    except service.AssessmentError:
        return RedirectResponse("/assessments", status_code=status.HTTP_303_SEE_OTHER)

    return _render(
        request,
        user,
        "assessments/finish.html",
        {"attempt_id": attempt_id},
    )


@router.post("/attempt/{attempt_id}/finish")
def attempt_finish_submit(
    attempt_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.finish_attempt(session, user_id=user.id, attempt_id=attempt_id)
    except service.AssessmentError:
        pass
    return RedirectResponse(
        f"/assessments/attempt/{attempt_id}/result",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/attempt/{attempt_id}/result", response_class=HTMLResponse)
def attempt_result(
    request: Request,
    attempt_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        attempt = service.get_attempt(session, attempt_id=attempt_id, user_id=user.id)
    except service.AssessmentError:
        return RedirectResponse("/assessments", status_code=status.HTTP_303_SEE_OTHER)

    if attempt.status != AttemptStatus.COMPLETED:
        return RedirectResponse(
            f"/assessments/attempt/{attempt.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    state = service.attempt_public_state(attempt)
    spec = session.get(Specialization, attempt.specialization_id)
    grade = session.get(Grade, attempt.target_grade_id)

    # Текущая категория
    current = service.current_category(session, user_id=user.id)
    current_data = None
    if current is not None:
        cat = session.get(Category, current.category_id)
        if cat is not None:
            current_data = {
                "status": current.status.value,
                "specialization": session.get(Specialization, cat.specialization_id),
                "grade": session.get(Grade, cat.grade_id),
            }

    cooldown = service.cooldown_status(session, user_id=user.id)

    return _render(
        request,
        user,
        "assessments/result.html",
        {
            "attempt": attempt,
            "spec": spec,
            "grade": grade,
            "state": state,
            "current": current_data,
            "cooldown": cooldown,
        },
    )