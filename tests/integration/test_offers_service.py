"""Интеграционные тесты сервиса приглашений.

Проверяют жизненный цикл: создание → просмотр → принятие/отклонение,
раскрытие контактов только после принятия, защиту от чужих приглашений.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.models import User, UserRole
from app.modules.auth.service import register_user
from app.modules.candidates.models import CandidateProfile
from app.modules.candidates.service import update_profile
from app.modules.employers.schemas import OfferCreate
from app.modules.employers.service import (
    CandidateNotFound,
    InvalidStatusTransition,
    OfferNotFound,
    create_offer,
    get_offer_for_candidate,
    get_offer_for_employer,
    list_candidate_offers,
    list_employer_offers,
    mark_offer_viewed,
    respond_to_offer,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

PREFIX = "offer-test-"


def _email() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email.like(f"{PREFIX}%")))
        session.commit()


def _make_candidate(session, phone: str = "+7 999 111-22-33") -> CandidateProfile:
    user = register_user(
        session,
        email=_email(),
        password="test1234",
        role=UserRole.CANDIDATE,
        full_name="Test Candidate",
    )
    update_profile(session, user_id=user.id, changes={"phone": phone})
    return session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == user.id)
    )


def _make_employer(session):
    return register_user(
        session,
        email=_email(),
        password="test1234",
        role=UserRole.EMPLOYER,
        full_name="Test Employer",
    )


def _offer_payload(candidate_profile_id: int) -> OfferCreate:
    return OfferCreate(
        candidate_profile_id=candidate_profile_id,
        title="Backend Developer",
        description="Приходите к нам",
        salary_from=200000,
        salary_to=300000,
        salary_gross=True,
        contact_method="Telegram: @hr",
    )


# --- Создание -------------------------------------------------------------


def test_create_offer():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )
        assert offer.status == "sent"
        assert offer.salary_from == 200000
        assert offer.salary_to == 300000
        assert offer.contacts is None


def test_create_offer_for_missing_candidate_raises():
    with SessionLocal() as session:
        employer = _make_employer(session)
        with pytest.raises(CandidateNotFound):
            create_offer(
                session,
                employer_user_id=employer.id,
                payload=_offer_payload(999_999),
            )


# --- Просмотр -------------------------------------------------------------


def test_mark_viewed_changes_status():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )

    with SessionLocal() as session:
        candidate_user = session.get(User, candidate.user_id)
        updated = mark_offer_viewed(
            session,
            offer_id=offer.id,
            candidate_user_id=candidate_user.id,
        )
        assert updated.status == "viewed"
        assert updated.viewed_at is not None


def test_mark_viewed_is_idempotent():
    """Повторный просмотр не меняет статус."""
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )
        candidate_user_id = candidate.user_id

    with SessionLocal() as session:
        mark_offer_viewed(
            session, offer_id=offer.id, candidate_user_id=candidate_user_id
        )
        second = mark_offer_viewed(
            session, offer_id=offer.id, candidate_user_id=candidate_user_id
        )
        assert second.status == "viewed"


# --- Принятие / отклонение ------------------------------------------------


def test_accept_offer_reveals_contacts_to_employer():
    with SessionLocal() as session:
        candidate = _make_candidate(session, phone="+7 999 000-11-22")
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )
        candidate_user_id = candidate.user_id
        employer_user_id = employer.id

    with SessionLocal() as session:
        responded = respond_to_offer(
            session,
            offer_id=offer.id,
            candidate_user_id=candidate_user_id,
            decision="accepted",
        )
        assert responded.status == "accepted"
        assert responded.responded_at is not None

    with SessionLocal() as session:
        employer_view = get_offer_for_employer(
            session, offer_id=offer.id, employer_user_id=employer_user_id
        )
        assert employer_view.contacts is not None
        assert employer_view.contacts.phone == "+7 999 000-11-22"


def test_reject_offer_does_not_reveal_contacts():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )
        candidate_user_id = candidate.user_id
        employer_user_id = employer.id

    with SessionLocal() as session:
        respond_to_offer(
            session,
            offer_id=offer.id,
            candidate_user_id=candidate_user_id,
            decision="rejected",
        )

    with SessionLocal() as session:
        employer_view = get_offer_for_employer(
            session, offer_id=offer.id, employer_user_id=employer_user_id
        )
        assert employer_view.status == "rejected"
        assert employer_view.contacts is None


def test_cannot_respond_twice():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )
        candidate_user_id = candidate.user_id

    with SessionLocal() as session:
        respond_to_offer(
            session,
            offer_id=offer.id,
            candidate_user_id=candidate_user_id,
            decision="accepted",
        )

    with SessionLocal() as session:
        with pytest.raises(InvalidStatusTransition):
            respond_to_offer(
                session,
                offer_id=offer.id,
                candidate_user_id=candidate_user_id,
                decision="rejected",
            )


def test_invalid_decision_rejected():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate.id),
        )
        candidate_user_id = candidate.user_id

    with SessionLocal() as session:
        with pytest.raises(InvalidStatusTransition):
            respond_to_offer(
                session,
                offer_id=offer.id,
                candidate_user_id=candidate_user_id,
                decision="maybe",
            )


# --- Изоляция доступа -----------------------------------------------------


def test_employer_cannot_see_foreign_offer():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer1 = _make_employer(session)
        employer2 = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer1.id,
            payload=_offer_payload(candidate.id),
        )
        employer2_id = employer2.id

    with SessionLocal() as session:
        with pytest.raises(OfferNotFound):
            get_offer_for_employer(
                session, offer_id=offer.id, employer_user_id=employer2_id
            )


def test_candidate_cannot_see_foreign_offer():
    with SessionLocal() as session:
        candidate1 = _make_candidate(session)
        candidate2 = _make_candidate(session)
        employer = _make_employer(session)
        offer = create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate1.id),
        )
        candidate2_user_id = candidate2.user_id

    with SessionLocal() as session:
        with pytest.raises(OfferNotFound):
            get_offer_for_candidate(
                session, offer_id=offer.id, candidate_user_id=candidate2_user_id
            )


# --- Списки ---------------------------------------------------------------


def test_employer_list_contains_created_offers():
    with SessionLocal() as session:
        candidate1 = _make_candidate(session)
        candidate2 = _make_candidate(session)
        employer = _make_employer(session)
        create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate1.id),
        )
        create_offer(
            session,
            employer_user_id=employer.id,
            payload=_offer_payload(candidate2.id),
        )
        employer_id = employer.id

    with SessionLocal() as session:
        offers = list_employer_offers(session, employer_id)
        assert len(offers) == 2


def test_candidate_list_contains_received_offers():
    with SessionLocal() as session:
        candidate = _make_candidate(session)
        employer1 = _make_employer(session)
        employer2 = _make_employer(session)
        create_offer(
            session,
            employer_user_id=employer1.id,
            payload=_offer_payload(candidate.id),
        )
        create_offer(
            session,
            employer_user_id=employer2.id,
            payload=_offer_payload(candidate.id),
        )
        candidate_user_id = candidate.user_id

    with SessionLocal() as session:
        offers = list_candidate_offers(session, candidate_user_id)
        assert len(offers) == 2