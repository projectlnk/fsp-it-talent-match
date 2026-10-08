"""HTML-страница профиля работодателя."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.employers import service
from app.web.templates import templates

router = APIRouter(prefix="/employer", tags=["employers-web"], include_in_schema=False)

_EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)


def _render_profile(request: Request, user: User, profile, *, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request=request,
        name="employers/profile.html",
        context={"user": user, "profile": profile, "error": error},
        status_code=status_code,
    )


@router.get("/profile", response_class=HTMLResponse)
def profile_page(
    request: Request,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    profile = service.get_profile_by_user_id(session, user.id)
    return _render_profile(request, user, profile)


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
        return _render_profile(request, user, profile, error=str(exc), status_code=400)
    return RedirectResponse("/employer/profile", status_code=status.HTTP_303_SEE_OTHER)