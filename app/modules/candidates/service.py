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
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.modules.candidates.schemas import (CandidateProfileUpdate, CandidateSkillCreate,
    CandidateSkillUpdate, CandidateExperienceCreate, CandidateExperienceUpdate, FspAchievementImport)

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


def _validate(schema, data):
    try:
        return schema.model_validate(data).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise CandidateError("Проверьте обязательные поля, числовые значения и порядок дат/зарплаты") from exc


def _lock_profile(session, user_id):
    profile = session.scalar(select(CandidateProfile).where(
        CandidateProfile.user_id == user_id).with_for_update().execution_options(populate_existing=True))
    if profile is None:
        raise ProfileNotFound()
    return profile


def _commit_skill(session):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        sqlite_duplicate = "UNIQUE constraint failed: candidate_skills.candidate_profile_id, candidate_skills.skill" in str(exc.orig)
        if constraint == "uq_candidate_skills_profile_skill" or sqlite_duplicate:
            raise SkillAlreadyExists() from exc
        raise


def update_profile(
    session: Session,
    *,
    user_id: int,
    changes: dict[str, Any],
) -> CandidateProfile:
    """Обновляет поля профиля. Передаются только изменённые поля."""
    profile = _lock_profile(session, user_id)
    changes = _validate(CandidateProfileUpdate, changes)
    _validate(CandidateProfileUpdate, {
        key: changes.get(key, getattr(profile, key))
        for key in ('desired_salary_from', 'desired_salary_to')
    })
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
    profile = _lock_profile(session, user_id)
    validated = _validate(CandidateSkillCreate, {"skill": skill, "level": level})
    normalized = validated['skill']
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
            level=validated['level'],
        )
    )
    _commit_skill(session)
    return get_profile_by_user_id(session, user_id)


def update_skill(
    session: Session,
    *,
    user_id: int,
    skill_id: int,
    changes: dict[str, Any],
) -> CandidateProfile:
    """Обновляет навык. Проверяет, что навык принадлежит профилю пользователя."""
    profile = _lock_profile(session, user_id)
    record = session.scalar(
        select(CandidateSkill).where(
            CandidateSkill.id == skill_id,
            CandidateSkill.candidate_profile_id == profile.id,
        )
    )
    if record is None:
        raise SkillNotFound()
    changes = _validate(CandidateSkillUpdate, changes)
    for key, value in changes.items():
        setattr(record, key, value)
    _commit_skill(session)
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
    profile = _lock_profile(session, user_id)
    data = _validate(CandidateExperienceCreate, data)
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
    profile = _lock_profile(session, user_id)
    record = session.scalar(
        select(CandidateExperience).where(
            CandidateExperience.id == experience_id,
            CandidateExperience.candidate_profile_id == profile.id,
        )
    )
    if record is None:
        raise ExperienceNotFound()
    changes = _validate(CandidateExperienceUpdate, changes)
    _validate(CandidateExperienceCreate, {
        key: changes.get(key, getattr(record, key))
        for key in ('company_name', 'position', 'started_at', 'ended_at', 'description', 'is_current')
    })
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


class FspRegistryInvalid(CandidateError):
    """Данные реестра не соответствуют договорённому контракту."""


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
    profile = _lock_profile(session, user_id)

    # Validate every achievement before changing a link or flushing any rows.
    try:
        achievements_data = [FspAchievementImport.model_validate(item).model_dump() for item in achievements_data]
    except (ValidationError, TypeError) as exc:
        raise FspRegistryInvalid("Некорректные данные реестра ФСП") from exc
    for item in achievements_data:
        if not isinstance(item, dict) or item.get('participant_id') != participant_id:
            raise FspParticipantNotFound("Реестр вернул достижение другого участника")

    # Проверим, что participant_id в ответе совпадает с запрошенным.
    # Это защита от подмены ответа.
    if not isinstance(profile_data, dict):
        raise FspRegistryInvalid("Некорректный профиль участника реестра ФСП")
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

    try:
        created, updated = _upsert_achievements(
            session, candidate_profile_id=profile.id, achievements_data=achievements_data,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise FspParticipantNotFound("Участник уже привязан или импорт конфликтует с другим запросом") from exc
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
    profile = _lock_profile(session, user_id)
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
