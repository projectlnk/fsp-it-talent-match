"""JSON API поиска кандидатов.

Ручки защищены ролью employer. Внутри используются сервис поиска и
ранжирование из matching.service. Контакты кандидатов не возвращаются.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.matching import service
from app.modules.matching.schemas import (
    CandidateCardRead,
    CandidateSearchQuery,
    CandidateSearchResult,
)

router = APIRouter(prefix="/matching", tags=["matching"])

_EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)


def _handle(exc: service.MatchingError) -> HTTPException:
    if isinstance(exc, service.CandidateNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    if isinstance(exc, service.InvalidFilter):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/candidates",
    response_model=CandidateSearchResult,
    summary="Поиск кандидатов",
)
def search_candidates(
    specialization: str | None = Query(default=None, max_length=100),
    grade: str | None = Query(default=None, max_length=50),
    skills: list[str] | None = Query(default=None),
    has_fsp_achievements: bool | None = Query(default=None),
    only_confirmed: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    """Ищет кандидатов по категориям, присвоенным после тестирования.

    Возвращает страницу карточек с объяснением ранжирования.
    Телефон и email кандидата не отдаются.
    """
    try:
        query = CandidateSearchQuery(
            specialization=specialization,
            grade=grade,
            skills=skills or [],
            has_fsp_achievements=has_fsp_achievements,
            only_confirmed=only_confirmed,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Некорректные параметры поиска: {exc}",
        ) from exc

    try:
        return service.search_candidates(session, query)
    except service.MatchingError as exc:
        raise _handle(exc) from exc


@router.get(
    "/candidates/{profile_id}",
    response_model=CandidateCardRead,
    summary="Карточка кандидата",
)
def get_candidate_card(
    profile_id: int,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    """Полная карточка кандидата без контактов.

    Внутри используется тот же сервис, что и для поиска: находим
    кандидата по id через отдельный метод сервиса.
    """
    try:
        return service.get_candidate_card(session, profile_id=profile_id)
    except service.MatchingError as exc:
        raise _handle(exc) from exc