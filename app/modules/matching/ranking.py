"""Ранжирование кандидатов и объяснимость выдачи.

Модуль не знает про БД и HTTP: на вход подаётся профиль со связанными
сущностями, на выходе — число и текстовые причины.

Формула зафиксирована и объяснима: работодатель видит не только место
кандидата в списке, но и причины.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.modules.candidates.models import CandidateProfile, FspAchievement

# --- Веса формулы --------------------------------------------------------

WEIGHT_TEST = 0.70
WEIGHT_FSP = 0.20
WEIGHT_RELEVANCE = 0.10

# Нормировка достижений: 5 «полновесных» дают максимум
FSP_MAX_WEIGHTED = 5.0

# Свежесть: достижения за последние N лет считаем актуальными
FRESHNESS_YEARS = 2
FRESHNESS_FRESH = 1.0
FRESHNESS_OLD = 0.5

# Вес призового места
PLACE_WEIGHTS: dict[int, float] = {
    1: 1.0,
    2: 0.7,
    3: 0.5,
}
RANK_WEIGHT = 0.5       # разряд/звание
PARTICIPATION_WEIGHT = 0.2  # просто участие

# Минимальный прирост, который попадает в reasons
REASON_THRESHOLD = 0.01


@dataclass
class RankingResult:
    score: float
    reasons: list[str] = field(default_factory=list)


def _achievement_weight(achievement: FspAchievement, today: date) -> float:
    """Вес одного достижения: призовое место × свежесть.

    Приоритет: место в соревновании, потом разряд, потом участие.
    """
    if achievement.place and achievement.place in PLACE_WEIGHTS:
        base = PLACE_WEIGHTS[achievement.place]
    elif achievement.rank:
        base = RANK_WEIGHT
    else:
        base = PARTICIPATION_WEIGHT

    if achievement.competition_date is None:
        freshness = FRESHNESS_OLD
    else:
        threshold = today - timedelta(days=FRESHNESS_YEARS * 365)
        freshness = FRESHNESS_FRESH if achievement.competition_date >= threshold else FRESHNESS_OLD

    return base * freshness


def _is_relevant(achievement: FspAchievement, specialization_code: str) -> bool:
    """Релевантно ли достижение текущей специализации кандидата."""
    return (
        achievement.discipline_code is not None
        and achievement.discipline_code.lower() == specialization_code.lower()
    )


def rank_candidate(
    profile: CandidateProfile,
    *,
    specialization_code: str,
    test_score: int | None,
    today: date | None = None,
) -> RankingResult:
    """Возвращает score и список причин.

    test_score — результат подтверждающего теста (0..100). Может быть None
    у неподтверждённых — тогда базовый компонент = 0.
    """
    if today is None:
        today = date.today()

    reasons: list[str] = []

    # 1. Результат теста
    normalized_test = (test_score or 0) / 100.0
    test_component = WEIGHT_TEST * normalized_test
    if test_score is not None:
        reasons.append(f"Результат теста: {test_score}%")

    # 2. Достижения ФСП
    achievements = list(profile.fsp_achievements)
    weighted_sum = 0.0
    for a in achievements:
        weighted_sum += _achievement_weight(a, today)
    fsp_component = WEIGHT_FSP * min(1.0, weighted_sum / FSP_MAX_WEIGHTED)

    if achievements:
        prizes = sum(1 for a in achievements if a.place in (1, 2, 3))
        ranks = sum(1 for a in achievements if a.rank and not a.place)
        parts = []
        if prizes:
            parts.append(f"призовых мест: {prizes}")
        if ranks:
            parts.append(f"разрядов: {ranks}")
        if not parts:
            parts.append(f"участий: {len(achievements)}")
        reasons.append("Достижения ФСП: " + ", ".join(parts))

    # 3. Релевантность дисциплины
    relevant = [a for a in achievements if _is_relevant(a, specialization_code)]
    relevance_component = 0.0
    if achievements:
        relevance_ratio = len(relevant) / len(achievements)
        relevance_component = WEIGHT_RELEVANCE * relevance_ratio
        if relevant:
            reasons.append(
                f"Релевантных дисциплине «{specialization_code}» достижений: {len(relevant)}"
            )

    score = (test_component + fsp_component + relevance_component) * 100.0
    return RankingResult(score=round(score, 2), reasons=reasons)


def explain_difference(
    candidate: RankingResult,
    baseline: RankingResult | None = None,
) -> str:
    """Короткое текстовое объяснение рейтинга для UI.

    Если baseline передан (например, средний по категории), формулируем
    как «выше/ниже среднего».
    """
    if baseline is None:
        return f"Рейтинг: {candidate.score:.1f} из 100"

    delta = candidate.score - baseline.score
    if abs(delta) < REASON_THRESHOLD:
        return "Рейтинг на уровне среднего по категории"
    direction = "выше" if delta > 0 else "ниже"
    return f"Рейтинг {direction} среднего по категории на {abs(delta):.1f}"