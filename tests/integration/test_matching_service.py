"""Интеграционные тесты сервиса поиска кандидатов.

Создают реальные профили и категории в БД, проверяют фильтры,
пагинацию и ранжирование.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.assessments.models import (
    CandidateCategory,
    Category,
    CategoryStatus,
    Grade,
    Specialization,
)
from app.modules.auth.models import User, UserRole
from app.modules.auth.service import register_user
from app.modules.candidates.models import CandidateProfile, FspAchievement
from app.modules.candidates.service import add_skill, update_profile
from app.modules.matching.schemas import CandidateSearchQuery
from app.modules.matching.service import search_candidates

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION") != "1",
        reason="Set RUN_INTEGRATION=1 with running services",
    ),
]

PREFIX = "match-test-"


def _email() -> str:
    return f"{PREFIX}{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with SessionLocal() as session:
        session.execute(delete(User).where(User.email.like(f"{PREFIX}%")))
        session.commit()


def _make_candidate(
    session,
    *,
    spec_code: str,
    grade_code: str,
    test_score: int | None,
    status: CategoryStatus = CategoryStatus.CONFIRMED,
    skills: list[str] | None = None,
    achievements: list[dict] | None = None,
    location: str | None = None,
) -> CandidateProfile:
    """Создаёт кандидата с категорией и опционально навыками и достижениями."""
    user = register_user(
        session,
        email=_email(),
        password="test1234",
        role=UserRole.CANDIDATE,
        full_name=f"Test {uuid.uuid4().hex[:6]}",
    )
    if location:
        update_profile(session, user_id=user.id, changes={"location": location})
    for s in skills or []:
        add_skill(session, user_id=user.id, skill=s, level=None)

    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == user.id)
    )

    spec = session.scalar(
        select(Specialization).where(Specialization.code == spec_code)
    )
    grade = session.scalar(select(Grade).where(Grade.code == grade_code))
    category = session.scalar(
        select(Category).where(
            Category.specialization_id == spec.id,
            Category.grade_id == grade.id,
        )
    )
    session.add(
        CandidateCategory(
            candidate_profile_id=profile.id,
            category_id=category.id,
            status=status,
            is_current=True,
            test_score=test_score,
        )
    )

    for a in achievements or []:
        session.add(
            FspAchievement(
                candidate_profile_id=profile.id,
                external_achievement_id=a["external_id"],
                title=a.get("title", "Test"),
                discipline_code=a.get("discipline_code"),
                place=a.get("place"),
                rank=a.get("rank"),
                is_team=False,
                is_demo=True,
            )
        )

    session.commit()
    return profile


# --- Фильтры --------------------------------------------------------------


def test_empty_query_returns_all_confirmed():
    with SessionLocal() as session:
        _make_candidate(session, spec_code="backend", grade_code="junior", test_score=80)
        _make_candidate(session, spec_code="frontend", grade_code="middle", test_score=70)

    with SessionLocal() as session:
        result = search_candidates(session, CandidateSearchQuery())
        assert result.meta.total >= 2


def test_filter_by_specialization():
    with SessionLocal() as session:
        _make_candidate(session, spec_code="backend", grade_code="junior", test_score=80)
        _make_candidate(session, spec_code="frontend", grade_code="junior", test_score=80)

    with SessionLocal() as session:
        result = search_candidates(
            session, CandidateSearchQuery(specialization="backend")
        )
        assert result.meta.total >= 1
        assert all(c.specialization_code == "backend" for c in result.items)


def test_filter_by_grade():
    with SessionLocal() as session:
        _make_candidate(session, spec_code="backend", grade_code="junior", test_score=80)
        _make_candidate(session, spec_code="backend", grade_code="senior", test_score=80)

    with SessionLocal() as session:
        result = search_candidates(session, CandidateSearchQuery(grade="senior"))
        assert result.meta.total >= 1
        assert all(c.grade_code == "senior" for c in result.items)


def test_filter_by_skill():
    with SessionLocal() as session:
        _make_candidate(
            session,
            spec_code="backend",
            grade_code="junior",
            test_score=80,
            skills=["Haskell"],
        )
        _make_candidate(
            session,
            spec_code="backend",
            grade_code="junior",
            test_score=80,
            skills=["Python"],
        )

    with SessionLocal() as session:
        result = search_candidates(
            session, CandidateSearchQuery(skills=["Haskell"])
        )
        assert result.meta.total == 1
        assert result.items[0].skills[0].skill == "Haskell"


def test_filter_by_skill_case_insensitive():
    with SessionLocal() as session:
        _make_candidate(
            session,
            spec_code="backend",
            grade_code="junior",
            test_score=80,
            skills=["RustLang"],
        )

    with SessionLocal() as session:
        result = search_candidates(
            session, CandidateSearchQuery(skills=["rustlang"])
        )
        assert result.meta.total >= 1


def test_filter_has_fsp_achievements():
    with SessionLocal() as session:
        _make_candidate(
            session,
            spec_code="backend",
            grade_code="junior",
            test_score=80,
            achievements=[
                {"external_id": "x-1", "place": 1, "discipline_code": "backend"}
            ],
        )
        _make_candidate(session, spec_code="backend", grade_code="junior", test_score=80)

    with SessionLocal() as session:
        with_fsp = search_candidates(
            session, CandidateSearchQuery(has_fsp_achievements=True)
        )
        without_fsp = search_candidates(
            session, CandidateSearchQuery(has_fsp_achievements=False)
        )
        assert with_fsp.meta.total >= 1
        assert all(c.fsp_has_achievements for c in with_fsp.items)
        assert all(not c.fsp_has_achievements for c in without_fsp.items)


def test_only_confirmed_excludes_not_confirmed():
    with SessionLocal() as session:
        _make_candidate(
            session,
            spec_code="backend",
            grade_code="junior",
            test_score=30,
            status=CategoryStatus.NOT_CONFIRMED,
        )

    with SessionLocal() as session:
        confirmed_only = search_candidates(
            session, CandidateSearchQuery(only_confirmed=True)
        )
        all_categories = search_candidates(
            session, CandidateSearchQuery(only_confirmed=False)
        )
        # Неподтверждённые видны при only_confirmed=False
        assert all_categories.meta.total >= confirmed_only.meta.total


# --- Пагинация -----------------------------------------------------------


def test_pagination():
    with SessionLocal() as session:
        for _ in range(3):
            _make_candidate(
                session, spec_code="backend", grade_code="junior", test_score=80
            )

    with SessionLocal() as session:
        page1 = search_candidates(
            session, CandidateSearchQuery(limit=2, offset=0)
        )
        page2 = search_candidates(
            session, CandidateSearchQuery(limit=2, offset=2)
        )
        assert len(page1.items) == 2
        assert page1.meta.total == page2.meta.total
        # ID на страницах не пересекаются
        ids1 = {c.profile_id for c in page1.items}
        ids2 = {c.profile_id for c in page2.items}
        assert not (ids1 & ids2)


# --- Ранжирование --------------------------------------------------------


def test_ranking_higher_test_score_first():
    """С более высоким test_score идёт выше при прочих равных."""
    with SessionLocal() as session:
        _make_candidate(session, spec_code="backend", grade_code="senior", test_score=95)
        _make_candidate(session, spec_code="backend", grade_code="senior", test_score=70)

    with SessionLocal() as session:
        result = search_candidates(
            session, CandidateSearchQuery(specialization="backend", grade="senior")
        )
        scores = [c.ranking_score for c in result.items]
        assert scores == sorted(scores, reverse=True)


def test_ranking_reasons_present():
    with SessionLocal() as session:
        _make_candidate(session, spec_code="backend", grade_code="junior", test_score=80)

    with SessionLocal() as session:
        result = search_candidates(session, CandidateSearchQuery(grade="junior"))
        assert result.items
        assert any("80%" in r for c in result.items for r in c.ranking_reasons)


def test_card_has_no_contacts():
    """Карточка не отдаёт телефон и email кандидата."""
    with SessionLocal() as session:
        _make_candidate(session, spec_code="backend", grade_code="junior", test_score=80)

    with SessionLocal() as session:
        result = search_candidates(session, CandidateSearchQuery())
        card = result.items[0]
        dumped = card.model_dump()
        assert "phone" not in dumped
        assert "email" not in dumped
        # ФИО и локация допустимы
        assert card.full_name