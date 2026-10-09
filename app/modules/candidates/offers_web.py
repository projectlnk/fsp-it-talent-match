"""HTML-страницы входящих приглашений для кандидата."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.employers import service as offers_service
from app.modules.employers.service import OfferError
from app.web.templates import templates

router = APIRouter(prefix="/candidate/offers", tags=["candidates-offers-web"], include_in_schema=False)

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


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


@router.get("", response_class=HTMLResponse)
def offers_list(
    request: Request,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    """Список всех входящих приглашений кандидата."""
    try:
        offers = offers_service.list_candidate_offers(session, user.id)
    except OfferError:
        offers = []
    return _render(request, user, "candidates/offers.html", {"offers": offers})


@router.get("/{offer_id}", response_class=HTMLResponse)
def offer_detail(
    request: Request,
    offer_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    """Карточка приглашения. Автоматически помечает просмотренным."""
    try:
        # Первое открытие переводит sent → viewed
        offers_service.mark_offer_viewed(
            session, offer_id=offer_id, candidate_user_id=user.id
        )
        offer = offers_service.get_offer_for_candidate(
            session, offer_id=offer_id, candidate_user_id=user.id
        )
    except OfferError:
        return RedirectResponse(
            "/candidate/offers", status_code=status.HTTP_303_SEE_OTHER
        )
    return _render(request, user, "candidates/offer_detail.html", {"offer": offer})


@router.post("/{offer_id}/respond", response_class=HTMLResponse)
def offer_respond(
    request: Request,
    offer_id: int,
    decision: str = Form(""),
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    """Принимает или отклоняет приглашение.

    `decision` приходит из формы со значениями `accepted` или `rejected`.
    Принятие раскрывает контакты работодателю.
    """
    if decision not in {"accepted", "rejected"}:
        return RedirectResponse(
            f"/candidate/offers/{offer_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        offers_service.respond_to_offer(
            session,
            offer_id=offer_id,
            candidate_user_id=user.id,
            decision=decision,
        )
    except OfferError:
        pass  # редирект покажет актуальное состояние

    return RedirectResponse(
        f"/candidate/offers/{offer_id}", status_code=status.HTTP_303_SEE_OTHER
    )