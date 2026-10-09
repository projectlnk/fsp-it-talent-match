"""Unit-тесты ранжирования кандидатов.

Формула проверяется на синтетических профилях с фиксированной датой.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.matching.ranking import (
    FSP_MAX_WEIGHTED,
    FRESHNESS_FRESH,
    FRESHNESS_OLD,
    PLACE_WEIGHTS,
    PARTICIPATION_WEIGHT,
    RANK_WEIGHT,
    WEIGHT_FSP,
    WEIGHT_RELEVANCE,
    WEIGHT_TEST,
    rank_candidate,
)

TODAY = date(2026, 10, 9)


class FakeAchievement:
    def __init__(
        self,
        place: int | None = None,
        rank: str | None = None,
        discipline_code: str | None = None,
        years_ago: int | None = 0,
    ):
        self.place = place
        self.rank = rank
        self.discipline_code = discipline_code
        self.competition_date = (
            None if years_ago is None else TODAY - timedelta(days=years_ago * 365)
        )
        self.title = "Test"
        self.is_team = False
        self.is_demo = True


class FakeProfile:
    def __init__(self, achievements=None):
        self.fsp_achievements = achievements or []


# --- Веса формулы --------------------------------------------------------


def test_weights_sum_to_one():
    """Все компоненты в сумме дают 100%."""
    assert abs(WEIGHT_TEST + WEIGHT_FSP + WEIGHT_RELEVANCE - 1.0) < 1e-9


def test_place_weights_ordered():
    """1 место весит больше 2, 2 больше 3, любое призовое больше участия."""
    assert PLACE_WEIGHTS[1] > PLACE_WEIGHTS[2] > PLACE_WEIGHTS[3]
    assert PLACE_WEIGHTS[3] > PARTICIPATION_WEIGHT
    assert RANK_WEIGHT > PARTICIPATION_WEIGHT


def test_freshness_weights():
    assert FRESHNESS_FRESH > FRESHNESS_OLD


# --- Компонент теста -----------------------------------------------------


def test_no_test_score_gives_zero_test_component():
    result = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=None,
        today=TODAY,
    )
    assert result.score == 0.0
    assert not any("тест" in r.lower() for r in result.reasons)


def test_perfect_test_score_gives_70_points():
    """100% теста без ФСП даёт ровно 70 баллов."""
    result = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=100,
        today=TODAY,
    )
    assert result.score == 70.0


def test_half_test_score_gives_35_points():
    result = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert result.score == 35.0


# --- Компонент достижений ------------------------------------------------


def test_achievements_increase_score():
    baseline = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    with_achievements = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert with_achievements.score > baseline.score


def test_first_place_weighs_more_than_third():
    first = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    third = rank_candidate(
        FakeProfile([FakeAchievement(place=3, discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert first.score > third.score


def test_rank_weighs_more_than_participation():
    with_rank = rank_candidate(
        FakeProfile([FakeAchievement(rank="КМС", discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    with_participation = rank_candidate(
        FakeProfile([FakeAchievement(discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert with_rank.score > with_participation.score


def test_old_achievement_weighs_less():
    fresh = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend", years_ago=1)]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    old = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend", years_ago=5)]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert fresh.score > old.score


def test_fsp_component_caps_at_max():
    """Больше FSP_MAX_WEIGHTED значимых достижений не увеличивают вклад."""
    many = [
        FakeAchievement(place=1, discipline_code="backend")
        for _ in range(int(FSP_MAX_WEIGHTED) + 5)
    ]
    capped = rank_candidate(
        FakeProfile(many),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    exact = rank_candidate(
        FakeProfile(
            [
                FakeAchievement(place=1, discipline_code="backend")
                for _ in range(int(FSP_MAX_WEIGHTED))
            ]
        ),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert capped.score == exact.score


# --- Релевантность дисциплины --------------------------------------------


def test_relevant_discipline_beats_irrelevant():
    relevant = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    irrelevant = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="robotics")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert relevant.score > irrelevant.score


def test_relevance_is_case_insensitive():
    upper = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="Backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    lower = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend")]),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert upper.score == lower.score


def test_mixed_achievements_partial_relevance():
    """Одно релевантное из двух даёт частичный бонус к рейтингу."""
    # baseline: тот же тест, но без достижений
    baseline = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    mixed = rank_candidate(
        FakeProfile(
            [
                FakeAchievement(place=1, discipline_code="backend"),
                FakeAchievement(place=1, discipline_code="robotics"),
            ]
        ),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    # Достижения повышают рейтинг, но смешанная релевантность даёт
    # меньше, чем полностью релевантный набор
    all_relevant = rank_candidate(
        FakeProfile(
            [
                FakeAchievement(place=1, discipline_code="backend"),
                FakeAchievement(place=1, discipline_code="backend"),
            ]
        ),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert mixed.score > baseline.score
    assert mixed.score < all_relevant.score


# --- Reasons --------------------------------------------------------------


def test_reasons_include_test_score():
    result = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=80,
        today=TODAY,
    )
    assert any("80%" in r for r in result.reasons)


def test_reasons_include_prizes():
    result = rank_candidate(
        FakeProfile(
            [
                FakeAchievement(place=1, discipline_code="backend"),
                FakeAchievement(place=3, discipline_code="backend"),
            ]
        ),
        specialization_code="backend",
        test_score=70,
        today=TODAY,
    )
    assert any("призовых мест" in r for r in result.reasons)


def test_reasons_include_rank_when_no_prizes():
    result = rank_candidate(
        FakeProfile([FakeAchievement(rank="КМС", discipline_code="backend")]),
        specialization_code="backend",
        test_score=70,
        today=TODAY,
    )
    assert any("разрядов" in r for r in result.reasons)


def test_reasons_include_relevance():
    result = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend")]),
        specialization_code="backend",
        test_score=70,
        today=TODAY,
    )
    assert any("Релевантных" in r for r in result.reasons)


# --- Сравнение ------------------------------------------------------------


def test_higher_test_beats_more_achievements():
    """По формуле тест весит больше достижений: 70% против 30%."""
    strong_test = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=100,
        today=TODAY,
    )
    lots_of_achievements = rank_candidate(
        FakeProfile(
            [
                FakeAchievement(place=1, discipline_code="backend")
                for _ in range(int(FSP_MAX_WEIGHTED))
            ]
        ),
        specialization_code="backend",
        test_score=50,
        today=TODAY,
    )
    assert strong_test.score > lots_of_achievements.score


def test_equal_test_achievements_break_tie():
    """При равном тесте достижения дают преимущество."""
    with_fsp = rank_candidate(
        FakeProfile([FakeAchievement(place=1, discipline_code="backend")]),
        specialization_code="backend",
        test_score=70,
        today=TODAY,
    )
    without_fsp = rank_candidate(
        FakeProfile(),
        specialization_code="backend",
        test_score=70,
        today=TODAY,
    )
    assert with_fsp.score > without_fsp.score