"""HTML-страница профиля кандидата: редактирование, навыки, опыт, ФСП ID."""
from __future__ import annotations

from datetime import date

import httpx
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.integrations.fsp.identity import FspIdentityClient
from app.integrations.fsp.registry import FspRegistryClient
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
    session: Session,
    *,
    error: str | None = None,
    fsp_error: str | None = None,
    status_code: int = status.HTTP_200_OK,
):
    fsp_link = service.get_fsp_link(session, user.id)
    fsp_achievements = service.list_fsp_achievements(session, user.id)
    return templates.TemplateResponse(
        request=request,
        name="candidates/profile.html",
        context={
            "user": user,
            "profile": profile,
            "work_formats": list(WorkFormat),
            "error": error,
            "fsp_link": fsp_link,
            "fsp_achievements": fsp_achievements,
            "fsp_error": fsp_error,
            "fsp_demo_ids": ["demo-1", "demo-2", "demo-3"],
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
    return _render_profile(request, user, profile, session)


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
            session,
            error="Зарплата «от» не может быть больше «до»",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        service.update_profile(session, user_id=user.id, changes=changes)
    except service.CandidateError as exc:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(
            request, user, profile, session, error=str(exc), status_code=400
        )

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


# --- ФСП ID ---------------------------------------------------------------


@router.post("/profile/fsp/link", response_class=HTMLResponse)
async def fsp_link(
    request: Request,
    participant_id: str = Form(...),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    """Привязывает участника ФСП и импортирует достижения.

    HTTP-вызовы делает роутер, запись в БД — сервис.
    """
    participant_id = participant_id.strip()
    if not participant_id:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(
            request,
            user,
            profile,
            session,
            fsp_error="Укажите ID участника ФСП",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            base_url=settings.fsp_base_url, timeout=10
        ) as client:
            identity = FspIdentityClient(client)
            registry = FspRegistryClient(client)
            profile_data = await identity.get_profile(participant_id)
            achievements_data = await registry.get_achievements(participant_id)
    except httpx.HTTPStatusError as exc:
        profile = service.get_profile_by_user_id(session, user.id)
        msg = (
            "Участник ФСП не найден"
            if exc.response.status_code == 404
            else "Ошибка реестра ФСП"
        )
        return _render_profile(
            request,
            user,
            profile,
            session,
            fsp_error=msg,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except httpx.RequestError:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(
            request,
            user,
            profile,
            session,
            fsp_error="Сервис ФСП временно недоступен",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        service.link_and_import_fsp(
            session,
            user_id=user.id,
            participant_id=participant_id,
            profile_data=profile_data,
            achievements_data=achievements_data,
        )
    except service.CandidateError as exc:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(
            request,
            user,
            profile,
            session,
            fsp_error=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/profile/fsp/unlink")
def fsp_unlink(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.unlink_fsp(session, user.id)
    except service.CandidateError:
        pass
    return RedirectResponse("/candidate/profile", status_code=status.HTTP_303_SEE_OTHER)