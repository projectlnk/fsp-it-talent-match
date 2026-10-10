"""Unit-тесты Pydantic-схем профилей."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.candidates.schemas import (
    CandidateExperienceCreate,
    CandidateProfileUpdate,
    CandidateSkillCreate,
)
from app.modules.candidates.models import WorkFormat
from app.modules.employers.schemas import EmployerProfileUpdate


# --- CandidateProfileUpdate ---------------------------------------------


def test_profile_update_accepts_all_fields():
    payload = CandidateProfileUpdate(
        full_name="Иван",
        phone="+7 999 000-00-00",
        location="Москва",
        desired_role="Backend",
        desired_salary_from=100000,
        desired_salary_to=200000,
        work_format=WorkFormat.REMOTE,
        experience_years=5,
    )
    assert payload.desired_salary_from == 100000


def test_profile_update_rejects_salary_from_greater_than_to():
    with pytest.raises(ValidationError):
        CandidateProfileUpdate(desired_salary_from=200000, desired_salary_to=100000)


def test_profile_update_allows_equal_salaries():
    payload = CandidateProfileUpdate(desired_salary_from=150000, desired_salary_to=150000)
    assert payload.desired_salary_from == payload.desired_salary_to


def test_profile_update_rejects_negative_salary():
    with pytest.raises(ValidationError):
        CandidateProfileUpdate(desired_salary_from=-1)


def test_profile_update_rejects_too_large_experience():
    with pytest.raises(ValidationError):
        CandidateProfileUpdate(experience_years=200)


def test_profile_update_partial_fields_ok():
    payload = CandidateProfileUpdate(desired_role="ML Engineer")
    dumped = payload.model_dump(exclude_unset=True)
    assert dumped == {"desired_role": "ML Engineer"}


# --- CandidateSkillCreate -----------------------------------------------


def test_skill_create_rejects_empty_name():
    with pytest.raises(ValidationError):
        CandidateSkillCreate(skill="")


def test_skill_create_accepts_level_none():
    payload = CandidateSkillCreate(skill="Python")
    assert payload.level is None


@pytest.mark.parametrize('level', [None, '', 'intern', 'junior', 'middle', 'senior', ' Middle '])
def test_skill_level_dropdown_values(level):
    from app.modules.candidates.schemas import CandidateSkillUpdate
    expected = level.strip().lower() or None if isinstance(level, str) else None
    assert CandidateSkillCreate(skill='Python', level=level).level == expected
    assert CandidateSkillUpdate(level=level).level == expected


def test_skill_level_rejects_arbitrary_text():
    from app.modules.candidates.schemas import CandidateSkillUpdate
    for schema in [CandidateSkillCreate, CandidateSkillUpdate]:
        with pytest.raises(ValidationError):
            schema(skill='Python', level='arbitrary')


# --- CandidateExperienceCreate ------------------------------------------


def test_experience_rejects_started_after_ended():
    with pytest.raises(ValidationError):
        CandidateExperienceCreate(
            company_name="ACME",
            position="Dev",
            started_at=date(2023, 1, 1),
            ended_at=date(2022, 1, 1),
        )


def test_experience_accepts_current_without_end_date():
    payload = CandidateExperienceCreate(
        company_name="ACME",
        position="Dev",
        started_at=date(2023, 1, 1),
        is_current=True,
    )
    assert payload.ended_at is None
    assert payload.is_current is True


# --- EmployerProfileUpdate ----------------------------------------------


def test_employer_update_rejects_invalid_email():
    with pytest.raises(ValidationError):
        EmployerProfileUpdate(contact_email="not-an-email")


def test_employer_update_accepts_valid_email():
    payload = EmployerProfileUpdate(contact_email="hr@example.ru")
    assert payload.contact_email == "hr@example.ru"


def test_employer_update_partial_fields_ok():
    payload = EmployerProfileUpdate(industry="IT")
    dumped = payload.model_dump(exclude_unset=True)
    assert dumped == {"industry": "IT"}
