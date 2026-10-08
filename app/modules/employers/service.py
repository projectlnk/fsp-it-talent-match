"""Бизнес-логика профиля работодателя.

Все операции идут от user_id: работодатель может работать только со своим
профилем.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employers.models import EmployerProfile


class EmployerError(Exception):
    """Базовая ошибка модуля employers."""


class ProfileNotFound(EmployerError):
    """Профиль работодателя не найден."""


def get_profile_by_user_id(session: Session, user_id: int) -> EmployerProfile:
    """Возвращает профиль по user_id или поднимает ProfileNotFound."""
    profile = session.scalar(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    )
    if profile is None:
        raise ProfileNotFound()
    return profile


def update_profile(
    session: Session,
    *,
    user_id: int,
    changes: dict[str, Any],
) -> EmployerProfile:
    """Обновляет поля профиля. Передаются только изменённые поля."""
    profile = get_profile_by_user_id(session, user_id)
    for key, value in changes.items():
        setattr(profile, key, value)
    session.commit()
    session.refresh(profile)
    return profile