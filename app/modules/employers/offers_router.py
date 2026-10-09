"""JSON API приглашений для работодателя.

Все ручки защищены ролью employer. Работают только с приглашениями,
отправленными текущим работодателем.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.employers import service
from app.modules.employers.schemas import OfferCreate, OfferRead

router = APIRouter(prefix="/employers/offers", tags=["employers-offers"])

_EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)


def _handle(exc: service.OfferError) -> HTTPException:
    if isinstance(exc, (service.OfferNotFound, service.CandidateNotFound)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, service.InvalidStatusTransition):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
    summary="Отправить приглашение кандидату",
)
def create_offer(
    payload: OfferCreate,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    """Создаёт адресное приглашение с зарплатой.

    Привязка к вакансии не требуется — это и есть основная механика
    подбора: работодатель зовёт конкретного человека.
    """
    try:
        return service.create_offer(
            session, employer_user_id=user.id, payload=payload
        )
    except service.OfferError as exc:
        raise _handle(exc) from exc


@router.get(
    "",
    response_model=list[OfferRead],
    summary="Отправленные приглашения",
)
def list_offers(
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    return service.list_employer_offers(session, user.id)


@router.get(
    "/{offer_id}",
    response_model=OfferRead,
    summary="Карточка приглашения",
)
def get_offer(
    offer_id: int,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.get_offer_for_employer(
            session, offer_id=offer_id, employer_user_id=user.id
        )
    except service.OfferError as exc:
        raise _handle(exc) from exc