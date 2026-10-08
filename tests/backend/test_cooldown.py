"""Unit-тесты констант кулдауна."""
from __future__ import annotations

from app.modules.assessments import service


def test_cooldown_positive():
    assert service.GRADE_CHANGE_COOLDOWN_DAYS > 0


def test_max_failed_attempts_positive():
    assert service.MAX_FAILED_ATTEMPTS_PER_GRADE > 0


def test_retry_block_positive():
    assert service.GRADE_RETRY_BLOCK_DAYS > 0


def test_cooldown_longer_than_retry_block():
    # Общий кулдаун на смену — строже, чем блок после провалов
    assert service.GRADE_CHANGE_COOLDOWN_DAYS > service.GRADE_RETRY_BLOCK_DAYS