"""JSON API привязки к ФСП ID.

Отделён от основного router.py модуля candidates, потому что здесь есть
асинхронные HTTP-вызовы к внешнему сервису (мок FSP ID). Сервисный слой
остаётся синхронным и не знает про HTTP.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.integrations.fsp.identity import FspIdentityClient
from app.integrations.fsp.registry import FspRegistryClient
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.candidates import service
from app.modules.candidates.schemas import (
    FspAchievementRead,
    FspImportResult,
    FspLinkRequest,
    FspParticipantRead,
    FspProfileRead,
    FspRegistryLinkRead,
)

router = APIRouter(prefix="/me/fsp", tags=["candidates-fsp"])

_CANDIDATE_ONLY = require_role(UserRole.CANDIDATE)


def _handle(exc: service.CandidateError) -> HTTPException:
    if isinstance(exc, service.FspParticipantNotFound):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc) or "Участник ФСП не может быть привязан",
        )
    if isinstance(exc, service.ProfileNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не найден")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _build_state(session: Session, user_id: int) -> FspProfileRead:
    """Собирает состояние связи и достижений кандидата."""
    link = service.get_fsp_link(session, user_id)
    achievements = service.list_fsp_achievements(session, user_id)
    return FspProfileRead(
        link=FspRegistryLinkRead.model_validate(link) if link else None,
        achievements=[FspAchievementRead.model_validate(a) for a in achievements],
        is_demo=True,
    )


@router.get("", response_model=FspProfileRead, summary="Связь с ФСП и достижения")
def get_state(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return _build_state(session, user.id)
    except service.CandidateError as exc:
        raise _handle(exc) from exc


@router.get(
    "/available",
    response_model=list[FspParticipantRead],
    summary="Участники, доступные в демо-реестре",
)
async def list_available_participants(
    user: User = Depends(_CANDIDATE_ONLY),
):
    """Подсказка для UI: какие participant_id можно ввести в демо.

    В боевой интеграции этот список формируется по поиску участника,
    а не отдаётся целиком.
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            base_url=settings.fsp_base_url, timeout=10
        ) as client:
            response = await client.get("/participants")
            response.raise_for_status()
            items = response.json()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис ФСП временно недоступен",
        ) from exc
    return [FspParticipantRead.model_validate(item) for item in items]


@router.post(
    "/link",
    response_model=FspProfileRead,
    summary="Привязать участника ФСП и импортировать достижения",
)
async def link_fsp(
    payload: FspLinkRequest,
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    settings = get_settings()
    participant_id = payload.participant_id.strip()
    if not participant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="participant_id обязателен",
        )

    try:
        async with httpx.AsyncClient(
            base_url=settings.fsp_base_url, timeout=10
        ) as client:
            identity = FspIdentityClient(client)
            registry = FspRegistryClient(client)
            profile_data = await identity.get_profile(participant_id)
            achievements_data = await registry.get_achievements(participant_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Участник ФСП не найден",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка реестра ФСП",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис ФСП временно недоступен",
        ) from exc

    try:
        service.link_and_import_fsp(
            session,
            user_id=user.id,
            participant_id=participant_id,
            profile_data=profile_data,
            achievements_data=achievements_data,
        )
    except service.CandidateError as exc:
        raise _handle(exc) from exc

    return _build_state(session, user.id)


@router.delete(
    "/link",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отвязать профиль от ФСП",
)
def unlink_fsp(
    user: User = Depends(_CANDIDATE_ONLY),
    session: Session = Depends(get_session),
):
    try:
        service.unlink_fsp(session, user.id)
    except service.CandidateError as exc:
        raise _handle(exc) from exc
    return None