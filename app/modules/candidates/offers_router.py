"""JSON API входящих приглашений для кандидата.

Кандидат видит только приглашения, адресованные ему. Может пометить
просмотренным и принять или отклонить.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.employers import service as offers_service
from app.modules.employers.schemas import OfferRead, OfferStatusUpdate

router = APIRouter(prefix="/candidates/me/offers", tags=["candidates-offers"])

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


def _handle(exc: offers_service.OfferError) -> HTTPException:
    if isinstance(exc, (offers_service.OfferNotFound, offers_service.CandidateNotFound)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, offers_service.InvalidStatusTransition):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "",
    response_model=list[OfferRead],
    summary="Входящие приглашения",
)
def list_incoming(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return offers_service.list_candidate_offers(session, user.id)
    except offers_service.OfferError as exc:
        raise _handle(exc) from exc


@router.get(
    "/{offer_id}",
    response_model=OfferRead,
    summary="Карточка входящего приглашения",
)
def get_incoming(
    offer_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return offers_service.get_offer_for_candidate(
            session, offer_id=offer_id, candidate_user_id=user.id
        )
    except offers_service.OfferError as exc:
        raise _handle(exc) from exc


@router.post(
    "/{offer_id}/view",
    response_model=OfferRead,
    summary="Пометить приглашение просмотренным",
)
def mark_viewed(
    offer_id: int,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return offers_service.mark_offer_viewed(
            session, offer_id=offer_id, candidate_user_id=user.id
        )
    except offers_service.OfferError as exc:
        raise _handle(exc) from exc


@router.post(
    "/{offer_id}/respond",
    response_model=OfferRead,
    summary="Принять или отклонить приглашение",
)
def respond(
    offer_id: int,
    payload: OfferStatusUpdate,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    """Принятие раскрывает контакты кандидата работодателю.

    Отклонение не раскрывает. Повторный ответ невозможен.
    """
    try:
        return offers_service.respond_to_offer(
            session,
            offer_id=offer_id,
            candidate_user_id=user.id,
            decision=payload.status,
        )
    except offers_service.OfferError as exc:
        raise _handle(exc) from exc