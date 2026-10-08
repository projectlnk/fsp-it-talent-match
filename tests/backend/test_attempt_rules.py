"""Unit-тесты констант и вспомогательных правил сервиса assessments."""
from __future__ import annotations

from app.modules.assessments import service


def test_thresholds_consistent():
    """Пороги: подтверждение — высокий, предложение ниже — средний, ниже — провал."""
    assert 0 < service.RETRY_LOWER_THRESHOLD < service.PASS_THRESHOLD < 1


def test_questions_per_attempt_positive():
    assert service.QUESTIONS_PER_ATTEMPT > 0


def test_pass_threshold_reasonable():
    # Не слишком мягко, не слишком строго — примерно 2/3
    assert 0.6 <= service.PASS_THRESHOLD <= 0.8


def test_retry_threshold_reasonable():
    assert 0.3 <= service.RETRY_LOWER_THRESHOLD <= 0.5