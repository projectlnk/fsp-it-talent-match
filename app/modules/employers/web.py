"""HTML-кабинет работодателя: профиль компании, поиск кандидатов, приглашения."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.employers import service
from app.modules.matching import service as matching_service
from app.modules.matching.schemas import CandidateSearchQuery
from app.web.templates import templates

router = APIRouter(prefix="/employer", tags=["employers-web"], include_in_schema=False)

_EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)


def _render(
    request: Request,
    user: User,
    template: str,
    context: dict,
    status_code: int = status.HTTP_200_OK,
):
    base = {"user": user}
    base.update(context)
    return templates.TemplateResponse(
        request=request, name=template, context=base, status_code=status_code
    )


# --- Профиль компании -----------------------------------------------------


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    profile = service.get_profile_by_user_id(session, user.id)
    return _render(
        request, user, "employers/profile.html", {"profile": profile, "error": None}
    )


@router.post("/profile", response_class=HTMLResponse)
def profile_update(
    request: Request,
    company_name: str = Form(...),
    description: str = Form(""),
    industry: str = Form(""),
    website: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    changes = {
        "company_name": company_name.strip(),
        "description": description.strip() or None,
        "industry": industry.strip() or None,
        "website": website.strip() or None,
        "contact_email": contact_email.strip() or None,
        "contact_phone": contact_phone.strip() or None,
    }
    try:
        service.update_profile(session, user_id=user.id, changes=changes)
    except service.EmployerError as exc:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render(
            request,
            user,
            "employers/profile.html",
            {"profile": profile, "error": str(exc)},
            status_code=400,
        )
    return RedirectResponse("/employer/profile", status_code=status.HTTP_303_SEE_OTHER)


# --- Поиск кандидатов -----------------------------------------------------


@router.get("/search", response_class=HTMLResponse)
def search_page(
    request: Request,
    specialization: str = "",
    grade: str = "",
    skills: str = "",
    has_fsp_achievements: str = "",
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    """Поиск кандидатов с фильтрами.

    Параметры идут через query string, форма отправляется GET-запросом —
    результат можно сохранить в закладки.
    """
    skills_list = [s.strip() for s in skills.split(",") if s.strip()]
    has_fsp: bool | None = None
    if has_fsp_achievements == "1":
        has_fsp = True
    elif has_fsp_achievements == "0":
        has_fsp = False

    query = CandidateSearchQuery(
        specialization=specialization or None,
        grade=grade or None,
        skills=skills_list,
        has_fsp_achievements=has_fsp,
        only_confirmed=True,
        limit=20,
        offset=0,
    )
    result = matching_service.search_candidates(session, query)

    return _render(
        request,
        user,
        "employers/search.html",
        {
            "result": result,
            "filters": {
                "specialization": specialization,
                "grade": grade,
                "skills": skills,
                "has_fsp_achievements": has_fsp_achievements,
            },
        },
    )


@router.get("/candidates/{profile_id}", response_class=HTMLResponse)
def candidate_card(
    request: Request,
    profile_id: int,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    """Карточка кандидата без контактов.

    Содержит форму приглашения: title, description, зарплата, способ связи.
    """
    try:
        card = matching_service.get_candidate_card(session, profile_id=profile_id)
    except matching_service.MatchingError:
        return RedirectResponse(
            "/employer/search", status_code=status.HTTP_303_SEE_OTHER
        )

    return _render(
        request,
        user,
        "employers/candidate_card.html",
        {"card": card, "error": None},
    )