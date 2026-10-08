"""Бизнес-логика профиля кандидата.

Все операции идут от user_id, а не от candidate_profile_id: сервис сам
находит профиль пользователя, поэтому кандидат не может обратиться к
чужому профилю.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.candidates.models import (
    CandidateExperience,
    CandidateProfile,
    CandidateSkill,
)


class CandidateError(Exception):
    """Базовая ошибка модуля candidates."""


class ProfileNotFound(CandidateError):
    """Профиль не найден."""


class SkillAlreadyExists(CandidateError):
    """Навык с таким именем уже есть в профиле."""


class SkillNotFound(CandidateError):
    """Навык не найден."""


class ExperienceNotFound(CandidateError):
    """Опыт не найден."""


def _load_profile(session: Session, user_id: int) -> CandidateProfile | None:
    """Загружает профиль с навыками и опытом одним запросом."""
    return session.scalar(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id)
        .options(
            selectinload(CandidateProfile.skills),
            selectinload(CandidateProfile.experiences),
        )
        .execution_options(populate_existing=True)
    )


def get_profile_by_user_id(session: Session, user_id: int) -> CandidateProfile:
    """Возвращает профиль по user_id или поднимает ProfileNotFound."""
    profile = _load_profile(session, user_id)
    if profile is None:
        raise ProfileNotFound()
    return profile


def update_profile(
    session: Session,
    *,
    user_id: int,
    changes: dict[str, Any],
) -> CandidateProfile:
    """Обновляет поля профиля. Передаются только изменённые поля."""
    profile = get_profile_by_user_id(session, user_id)
    for key, value in changes.items():
        setattr(profile, key, value)
    session.commit()
    return get_profile_by_user_id(session, user_id)


# --- Навыки --------------------------------------------------------------


def add_skill(
    session: Session,
    *,
    user_id: int,
    skill: str,
    level: str | None,
) -> CandidateProfile:
    """Добавляет навык. Поднимает SkillAlreadyExists при дубле."""
    profile = get_profile_by_user_id(session, user_id)
    normalized = skill.strip()
    existing = session.scalar(
        select(CandidateSkill).where(
            CandidateSkill.candidate_profile_id == profile.id,
            CandidateSkill.skill == normalized,
        )
    )
    if existing is not None:
        raise SkillAlreadyExists(normalized)
    session.add(
        CandidateSkill(
            candidate_profile_id=profile.id,
            skill=normalized,
            level=level,
        )
    )
    session.commit()
    return get_profile_by_user_id(session, user_id)


def update_skill(
    session: Session,
    *,
    user_id: int,
    skill_id: int,
    changes: dict[str, Any],
) -> CandidateProfile:
    """Обновляет навык. Проверяет, что навык принадлежит профилю пользователя."""
    profile = get_profile_by_user_id(session, user_id)
    record = session.scalar(
        select(CandidateSkill).where(
            CandidateSkill.id == skill_id,
            CandidateSkill.candidate_profile_id == profile.id,
        )
    )
    if record is None:
        raise SkillNotFound()
    for key, value in changes.items():
        setattr(record, key, value)
    session.commit()
    return get_profile_by_user_id(session, user_id)


def delete_skill(session: Session, *, user_id: int, skill_id: int) -> CandidateProfile:
    profile = get_profile_by_user_id(session, user_id)
    record = session.scalar(
        select(CandidateSkill).where(
            CandidateSkill.id == skill_id,
            CandidateSkill.candidate_profile_id == profile.id,
        )
    )
    if record is None:
        raise SkillNotFound()
    session.delete(record)
    session.commit()
    return get_profile_by_user_id(session, user_id)


# --- Опыт ----------------------------------------------------------------


def add_experience(
    session: Session,
    *,
    user_id: int,
    data: dict[str, Any],
) -> CandidateProfile:
    profile = get_profile_by_user_id(session, user_id)
    session.add(CandidateExperience(candidate_profile_id=profile.id, **data))
    session.commit()
    return get_profile_by_user_id(session, user_id)


def update_experience(
    session: Session,
    *,
    user_id: int,
    experience_id: int,
    changes: dict[str, Any],
) -> CandidateProfile:
    profile = get_profile_by_user_id(session, user_id)
    record = session.scalar(
        select(CandidateExperience).where(
            CandidateExperience.id == experience_id,
            CandidateExperience.candidate_profile_id == profile.id,
        )
    )
    if record is None:
        raise ExperienceNotFound()
    for key, value in changes.items():
        setattr(record, key, value)
    session.commit()
    return get_profile_by_user_id(session, user_id)


def delete_experience(
    session: Session,
    *,
    user_id: int,
    experience_id: int,
) -> CandidateProfile:
    profile = get_profile_by_user_id(session, user_id)
    record = session.scalar(
        select(CandidateExperience).where(
            CandidateExperience.id == experience_id,
            CandidateExperience.candidate_profile_id == profile.id,
        )
    )
    if record is None:
        raise ExperienceNotFound()
    session.delete(record)
    session.commit()
    return get_profile_by_user_id(session, user_id)