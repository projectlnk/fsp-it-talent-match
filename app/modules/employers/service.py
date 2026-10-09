"""Бизнес-логика профиля работодателя.

Все операции идут от user_id: работодатель может работать только со своим
профилем.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.assessments.models import CandidateCategory, Category, Grade, Specialization
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import (
    EmployerProfile,
    Offer,
    OfferStatus,
)
from app.modules.employers.schemas import (
    CandidateBrief,
    ContactsRead,
    EmployerProfileBrief,
    OfferCreate,
    OfferRead,
)


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

# --- Приглашения ----------------------------------------------------------


class OfferError(Exception):
    """Базовая ошибка модуля приглашений."""


class OfferNotFound(OfferError):
    """Приглашение не найдено."""


class CandidateNotFound(OfferError):
    """Кандидат не найден."""


class InvalidStatusTransition(OfferError):
    """Недопустимый переход статуса."""


def _candidate_brief(session: Session, profile: CandidateProfile) -> CandidateBrief:
    """Собирает публичный минимум о кандидате без контактов."""
    row = session.execute(
        select(Category, Specialization, Grade)
        .join(CandidateCategory, CandidateCategory.category_id == Category.id)
        .join(Specialization, Specialization.id == Category.specialization_id)
        .join(Grade, Grade.id == Category.grade_id)
        .where(
            CandidateCategory.candidate_profile_id == profile.id,
            CandidateCategory.is_current.is_(True),
        )
    ).first()

    if row is None:
        return CandidateBrief(profile_id=profile.id, full_name=profile.full_name)

    _, spec, grade = row
    return CandidateBrief(
        profile_id=profile.id,
        full_name=profile.full_name,
        specialization_code=spec.code,
        specialization_name=spec.name,
        grade_code=grade.code,
        grade_name=grade.name,
    )


def _to_offer_read(
    session: Session,
    offer: Offer,
    *,
    reveal_contacts: bool,
) -> OfferRead:
    """Сериализует Offer. Контакты — только при reveal_contacts=True."""
    employer = session.get(EmployerProfile, offer.employer_profile_id)
    candidate_profile = session.get(CandidateProfile, offer.candidate_profile_id)

    contacts = None
    if reveal_contacts and candidate_profile is not None:
        candidate_user = candidate_profile.user if hasattr(candidate_profile, "user") else None
        # email пользователя достаём через сессию, чтобы не зависеть от relationship
        from app.modules.auth.models import User

        user = session.get(User, candidate_profile.user_id)
        contacts = ContactsRead(
            email=user.email if user else None,
            phone=candidate_profile.phone,
        )

    return OfferRead(
        id=offer.id,
        status=offer.status.value,
        title=offer.title,
        description=offer.description,
        salary_from=offer.salary_from,
        salary_to=offer.salary_to,
        salary_currency=offer.salary_currency.value,
        salary_gross=offer.salary_gross,
        contact_method=offer.contact_method,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
        viewed_at=offer.viewed_at,
        responded_at=offer.responded_at,
        employer=EmployerProfileBrief.model_validate(employer),
        candidate=_candidate_brief(session, candidate_profile),
        contacts=contacts,
    )


def create_offer(
    session: Session,
    *,
    employer_user_id: int,
    payload: OfferCreate,
) -> OfferRead:
    """Создаёт приглашение от имени работодателя.

    Приглашение не привязано к вакансии. Зарплата обязательна.
    """
    employer = get_profile_by_user_id(session, employer_user_id)
    candidate = session.get(CandidateProfile, payload.candidate_profile_id)
    if candidate is None:
        raise CandidateNotFound("Кандидат не найден")

    offer = Offer(
        employer_profile_id=employer.id,
        candidate_profile_id=candidate.id,
        title=payload.title.strip(),
        description=payload.description,
        salary_from=payload.salary_from,
        salary_to=payload.salary_to,
        salary_gross=payload.salary_gross,
        contact_method=payload.contact_method,
        status=OfferStatus.SENT,
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return _to_offer_read(session, offer, reveal_contacts=False)


def list_employer_offers(session: Session, employer_user_id: int) -> list[OfferRead]:
    """Все приглашения, отправленные текущим работодателем."""
    employer = get_profile_by_user_id(session, employer_user_id)
    offers = session.scalars(
        select(Offer)
        .where(Offer.employer_profile_id == employer.id)
        .order_by(Offer.id.desc())
    ).all()
    return [
        _to_offer_read(session, o, reveal_contacts=o.status == OfferStatus.ACCEPTED)
        for o in offers
    ]


def list_candidate_offers(session: Session, candidate_user_id: int) -> list[OfferRead]:
    """Все приглашения, полученные текущим кандидатом."""
    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == candidate_user_id)
    )
    if profile is None:
        raise CandidateNotFound("Профиль не найден")

    offers = session.scalars(
        select(Offer)
        .where(Offer.candidate_profile_id == profile.id)
        .order_by(Offer.id.desc())
    ).all()
    return [_to_offer_read(session, o, reveal_contacts=False) for o in offers]


def get_offer_for_employer(
    session: Session, *, offer_id: int, employer_user_id: int
) -> OfferRead:
    """Возвращает приглашение, принадлежащее работодателю."""
    employer = get_profile_by_user_id(session, employer_user_id)
    offer = session.scalar(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.employer_profile_id == employer.id,
        )
    )
    if offer is None:
        raise OfferNotFound("Приглашение не найдено")
    return _to_offer_read(session, offer, reveal_contacts=offer.status == OfferStatus.ACCEPTED)


def get_offer_for_candidate(
    session: Session, *, offer_id: int, candidate_user_id: int
) -> OfferRead:
    """Возвращает приглашение, адресованное кандидату."""
    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == candidate_user_id)
    )
    if profile is None:
        raise CandidateNotFound("Профиль не найден")
    offer = session.scalar(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.candidate_profile_id == profile.id,
        )
    )
    if offer is None:
        raise OfferNotFound("Приглашение не найдено")
    return _to_offer_read(session, offer, reveal_contacts=False)


def mark_offer_viewed(
    session: Session, *, offer_id: int, candidate_user_id: int
) -> OfferRead:
    """Кандидат открыл приглашение. Переход sent → viewed."""
    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == candidate_user_id)
    )
    if profile is None:
        raise CandidateNotFound("Профиль не найден")
    offer = session.scalar(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.candidate_profile_id == profile.id,
        )
    )
    if offer is None:
        raise OfferNotFound("Приглашение не найдено")

    if offer.status == OfferStatus.SENT:
        offer.status = OfferStatus.VIEWED
        offer.viewed_at = datetime.now(UTC)
        session.commit()
        session.refresh(offer)

    return _to_offer_read(session, offer, reveal_contacts=False)


def respond_to_offer(
    session: Session,
    *,
    offer_id: int,
    candidate_user_id: int,
    decision: str,
) -> OfferRead:
    """Кандидат принимает или отклоняет приглашение.

    После принятия контакты раскрываются работодателю.
    """
    if decision not in {"accepted", "rejected"}:
        raise InvalidStatusTransition("Решение должно быть accepted или rejected")

    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == candidate_user_id)
    )
    if profile is None:
        raise CandidateNotFound("Профиль не найден")
    offer = session.scalar(
        select(Offer).where(
            Offer.id == offer_id,
            Offer.candidate_profile_id == profile.id,
        )
    )
    if offer is None:
        raise OfferNotFound("Приглашение не найдено")

    if offer.status in {OfferStatus.ACCEPTED, OfferStatus.REJECTED}:
        raise InvalidStatusTransition("Приглашение уже обработано")

    offer.status = OfferStatus.ACCEPTED if decision == "accepted" else OfferStatus.REJECTED
    offer.responded_at = datetime.now(UTC)
    if offer.viewed_at is None:
        offer.viewed_at = offer.responded_at
    session.commit()
    session.refresh(offer)
    return _to_offer_read(session, offer, reveal_contacts=False)