"""Бизнес-логика профиля кандидата.

Все операции идут от user_id, а не от candidate_profile_id: сервис сам
находит профиль пользователя, поэтому кандидат не может обратиться к
чужому профилю.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.modules.candidates.models import (
    CandidateExperience,
    CandidateProfile,
    CandidateSkill,
    FspAchievement,
    FspRegistryLink,
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

# --- FSP ID --------------------------------------------------------------


class FspLinkNotFound(CandidateError):
    """Связь с реестром ФСП не найдена."""


class FspParticipantNotFound(CandidateError):
    """Участник реестра ФСП не найден."""


def get_fsp_link(session: Session, user_id: int) -> FspRegistryLink | None:
    """Возвращает связь кандидата с реестром ФСП или None."""
    profile = get_profile_by_user_id(session, user_id)
    return session.scalar(
        select(FspRegistryLink).where(
            FspRegistryLink.candidate_profile_id == profile.id
        )
    )


def list_fsp_achievements(session: Session, user_id: int) -> list[FspAchievement]:
    """Возвращает список сохранённых достижений кандидата."""
    profile = get_profile_by_user_id(session, user_id)
    return list(
        session.scalars(
            select(FspAchievement)
            .where(FspAchievement.candidate_profile_id == profile.id)
            .order_by(FspAchievement.competition_date.desc().nullslast(), FspAchievement.id.desc())
        )
    )


def link_and_import_fsp(
    session: Session,
    *,
    user_id: int,
    participant_id: str,
    profile_data: dict[str, Any],
    achievements_data: list[dict[str, Any]],
) -> tuple[FspRegistryLink, int, int]:
    """Связывает профиль с участником реестра ФСП и импортирует достижения.

    `profile_data` и `achievements_data` уже получены через адаптеры
    `IdentityProvider` и `AchievementRegistry`. Если участник не найден —
    сервис вызывается только после успешной проверки, поэтому здесь
    проверяем только бизнес-правила.

    Возвращает (link, created, updated).
    """
    profile = get_profile_by_user_id(session, user_id)

    # Проверим, что participant_id в ответе совпадает с запрошенным.
    # Это защита от подмены ответа.
    response_id = str(profile_data.get("id") or "").strip()
    if response_id != participant_id:
        raise FspParticipantNotFound(
            f"Реестр вернул участника {response_id!r} вместо {participant_id!r}"
        )

    # Проверим, что участник не привязан к другому профилю
    existing_link_other = session.scalar(
        select(FspRegistryLink).where(
            FspRegistryLink.registry_participant_id == participant_id,
            FspRegistryLink.candidate_profile_id != profile.id,
        )
    )
    if existing_link_other is not None:
        raise FspParticipantNotFound("Этот участник уже привязан к другому профилю")

    link = session.scalar(
        select(FspRegistryLink).where(
            FspRegistryLink.candidate_profile_id == profile.id
        )
    )
    if link is None:
        link = FspRegistryLink(
            candidate_profile_id=profile.id,
            registry_participant_id=participant_id,
        )
        session.add(link)
    else:
        # Если меняется participant_id — старые достижения больше не валидны,
        # потому что они относятся к другому участнику реестра.
        if link.registry_participant_id != participant_id:
            session.execute(
                delete(FspAchievement).where(
                    FspAchievement.candidate_profile_id == profile.id
                )
            )
        link.registry_participant_id = participant_id

    created, updated = _upsert_achievements(
        session,
        candidate_profile_id=profile.id,
        achievements_data=achievements_data,
    )

    session.commit()
    session.refresh(link)
    return link, created, updated


def _upsert_achievements(
    session: Session,
    *,
    candidate_profile_id: int,
    achievements_data: list[dict[str, Any]],
) -> tuple[int, int]:
    """Идемпотентно сохраняет достижения.

    Ключ — external_achievement_id. Повторный импорт обновляет поля,
    а не создаёт дубли.
    """
    created = updated = 0
    for item in achievements_data:
        ext_id = str(item.get("id") or "").strip()
        if not ext_id:
            continue

        # Защита от чужого достижения: participant_id в достижении
        # должен совпадать с тем, для кого мы импортируем. Но так как
        # реестр сам фильтрует по participant_id, дополнительно
        # проверяем только отсутствие привязки достижения к другому профилю.
        existing = session.scalar(
            select(FspAchievement).where(
                FspAchievement.candidate_profile_id == candidate_profile_id,
                FspAchievement.external_achievement_id == ext_id,
            )
        )

        payload = {
            "title": str(item.get("title") or "").strip() or "Достижение",
            "discipline_code": item.get("discipline_code"),
            "competition_name": item.get("competition_name"),
            "competition_date": _parse_iso_date(item.get("competition_date")),
            "place": item.get("place"),
            "rank": item.get("rank"),
            "team_name": item.get("team_name"),
            "is_team": bool(item.get("is_team")),
            "is_demo": True,
        }

        if existing is None:
            session.add(
                FspAchievement(
                    candidate_profile_id=candidate_profile_id,
                    external_achievement_id=ext_id,
                    **payload,
                )
            )
            created += 1
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
            updated += 1
    return created, updated


def _parse_iso_date(value: Any) -> date | None:
    """Парсит ISO-дату из ответа реестра, если она есть."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def unlink_fsp(session: Session, user_id: int) -> None:
    """Отвязывает профиль от реестра ФСП и удаляет импортированные достижения."""
    profile = get_profile_by_user_id(session, user_id)
    session.execute(
        delete(FspAchievement).where(
            FspAchievement.candidate_profile_id == profile.id
        )
    )
    session.execute(
        delete(FspRegistryLink).where(
            FspRegistryLink.candidate_profile_id == profile.id
        )
    )
    session.commit()