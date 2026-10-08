"""JSON API профиля работодателя.

Эндпоинты защищены ролью employer и работают с профилем текущего пользователя.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.employers import service
from app.modules.employers.schemas import (
    EmployerProfileRead,
    EmployerProfileUpdate,
)

router = APIRouter(prefix="/employers", tags=["employers"])

_EMPLOYER_ONLY = require_role(UserRole.EMPLOYER)


def _handle_service_error(exc: service.EmployerError) -> HTTPException:
    if isinstance(exc, service.ProfileNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не найден")
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный запрос")


@router.get(
    "/me",
    response_model=EmployerProfileRead,
    summary="Профиль текущего работодателя",
)
def get_me(
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    try:
        return service.get_profile_by_user_id(session, user.id)
    except service.EmployerError as exc:
        raise _handle_service_error(exc) from exc


@router.patch(
    "/me",
    response_model=EmployerProfileRead,
    summary="Обновить профиль компании",
)
def update_me(
    payload: EmployerProfileUpdate,
    user: User = Depends(_EMPLOYER_ONLY),
    session: Session = Depends(get_session),
):
    changes = payload.model_dump(exclude_unset=True)
    try:
        return service.update_profile(session, user_id=user.id, changes=changes)
    except service.EmployerError as exc:
        raise _handle_service_error(exc) from exc