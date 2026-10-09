"""Unit-тесты схем приглашений."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.employers.schemas import (
    OfferCreate,
    OfferStatusUpdate,
)


def test_offer_create_accepts_valid_payload():
    payload = OfferCreate(
        candidate_profile_id=1,
        title="Backend Developer",
        description="Приходите",
        salary_from=200000,
        salary_to=300000,
        salary_gross=True,
        contact_method="Telegram: @hr",
    )
    assert payload.salary_from == 200000
    assert payload.salary_gross is True


def test_offer_create_rejects_salary_from_greater_than_to():
    with pytest.raises(ValidationError):
        OfferCreate(
            candidate_profile_id=1,
            title="X",
            salary_from=300000,
            salary_to=100000,
        )


def test_offer_create_allows_equal_salaries():
    payload = OfferCreate(
        candidate_profile_id=1,
        title="X",
        salary_from=250000,
        salary_to=250000,
    )
    assert payload.salary_from == payload.salary_to


def test_offer_create_rejects_negative_salary():
    with pytest.raises(ValidationError):
        OfferCreate(
            candidate_profile_id=1,
            title="X",
            salary_from=-1,
            salary_to=100000,
        )


def test_offer_create_rejects_empty_title():
    with pytest.raises(ValidationError):
        OfferCreate(
            candidate_profile_id=1,
            title="",
            salary_from=100000,
            salary_to=200000,
        )


def test_offer_create_rejects_zero_candidate_id():
    with pytest.raises(ValidationError):
        OfferCreate(
            candidate_profile_id=0,
            title="X",
            salary_from=100000,
            salary_to=200000,
        )


def test_offer_status_update_accepts_allowed_values():
    for value in ("viewed", "accepted", "rejected"):
        payload = OfferStatusUpdate(status=value)
        assert payload.status == value


def test_offer_status_update_rejects_sent():
    """sent ставится сервисом, а не через API."""
    with pytest.raises(ValidationError):
        OfferStatusUpdate(status="sent")


def test_offer_status_update_rejects_garbage():
    with pytest.raises(ValidationError):
        OfferStatusUpdate(status="not-a-status")