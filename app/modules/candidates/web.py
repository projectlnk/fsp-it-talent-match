"""HTML-страница профиля кандидата: редактирование, навыки, опыт."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.candidates import service
from app.modules.candidates.models import WorkFormat
from app.web.templates import templates

router = APIRouter(prefix="/candidate", tags=["candidates-web"], include_in_schema=False)

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


def _parse_date(value: str | None) -> date | None:
    """Парсит YYYY-MM-DD. Пустая строка → None."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _render_profile(
    request: Request,
    user: User,
    profile,
    *,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
):
    return templates.TemplateResponse(
        request=request,
        name="candidates/profile.html",
        context={
            "user": user,
            "profile": profile,
            "work_formats": list(WorkFormat),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    profile = service.get_profile_by_user_id(session, user.id)
    return _render_profile(request, user, profile)


@router.post("/profile", response_class=HTMLResponse)
def profile_update(
    request: Request,
    full_name: str = Form(...),
    phone: str = Form(""),
    location: str = Form(""),
    about: str = Form(""),
    desired_role: str = Form(""),
    desired_salary_from: str = Form(""),
    desired_salary_to: str = Form(""),
    work_format: str = Form(""),
    experience_years: str = Form(""),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    def _int_or_none(value: str) -> int | None:
        value = value.strip()
        return int(value) if value.isdigit() else None

    changes: dict = {
        "full_name": full_name.strip(),
        "phone": phone.strip() or None,
        "location": location.strip() or None,
        "about": about.strip() or None,
        "desired_role": desired_role.strip() or None,
        "desired_salary_from": _int_or_none(desired_salary_from),
        "desired_salary_to": _int_or_none(desired_salary_to),
        "experience_years": _int_or_none(experience_years),
        "work_format": None,
    }
    if work_format:
        try:
            changes["work_format"] = WorkFormat(work_format)
        except ValueError:
            changes["work_format"] = None

    if (
        changes["desired_salary_from"] is not None
        and changes["desired_salary_to"] is not None
        and changes["desired_salary_from"] > changes["desired_salary_to"]
    ):
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(
            request,
            user,
            profile,
            error="Зарплата «от» не может быть больше «до»",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        service.update_profile(session, user_id=user.id, changes=changes)
    except service.CandidateError as exc:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(request, user, profile, error=str(exc), status_code=400)

    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)


# --- Навыки --------------------------------------------------------------


@router.post("/profile/skills")
def skill_add(
    skill: str = Form(...),
    level: str = Form(""),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    if skill.strip():
        try:
            service.add_skill(
                session, user_id=user.id, skill=skill, level=level.strip() or None
            )
        except service.SkillAlreadyExists:
            pass  # молча игнорируем дубль, страница покажет актуальное состояние
    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/profile/skills/{skill_id}/delete")
def skill_delete(
    skill_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.delete_skill(session, user_id=user.id, skill_id=skill_id)
    except service.SkillNotFound:
        pass
    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)


# --- Опыт ----------------------------------------------------------------


@router.post("/profile/experiences")
def experience_add(
    company_name: str = Form(...),
    position: str = Form(...),
    started_at: str = Form(""),
    ended_at: str = Form(""),
    description: str = Form(""),
    is_current: str = Form(""),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    if company_name.strip() and position.strip():
        service.add_experience(
            session,
            user_id=user.id,
            data={
                "company_name": company_name.strip(),
                "position": position.strip(),
                "started_at": _parse_date(started_at),
                "ended_at": _parse_date(ended_at),
                "description": description.strip() or None,
                "is_current": bool(is_current),
            },
        )
    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/profile/experiences/{experience_id}/delete")
def experience_delete(
    experience_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.delete_experience(session, user_id=user.id, experience_id=experience_id)
    except service.ExperienceNotFound:
        pass
    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)