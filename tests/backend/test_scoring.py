"""Unit-тесты взвешенного подсчёта."""
from __future__ import annotations

from app.modules.assessments.service import _weighted_score


class FakeAnswer:
    def __init__(self, difficulty, is_correct):
        self.question_snapshot = {"difficulty": difficulty}
        self.is_correct = is_correct


def test_all_correct():
    answers = [FakeAnswer(1, True), FakeAnswer(3, True), FakeAnswer(5, True)]
    assert _weighted_score(answers) == 1.0


def test_all_wrong():
    answers = [FakeAnswer(1, False), FakeAnswer(3, False), FakeAnswer(5, False)]
    assert _weighted_score(answers) == 0.0


def test_weighted_better_than_naive():
    # 2 простых правильных, 1 сложный неправильный
    # Наивно: 2/3 = 0.66
    # Взвешенно: (1+1)/(1+1+5) = 2/7 ≈ 0.29
    answers = [FakeAnswer(1, True), FakeAnswer(1, True), FakeAnswer(5, False)]
    assert _weighted_score(answers) < 0.5


def test_correct_hard_beats_correct_easy():
    # 1 сложный правильный: 5/(5+1+1) = 0.71
    # 2 простых правильных: 2/(5+1+1) = 0.29
    hard_correct = [FakeAnswer(5, True), FakeAnswer(1, False), FakeAnswer(1, False)]
    easy_correct = [FakeAnswer(5, False), FakeAnswer(1, True), FakeAnswer(1, True)]
    assert _weighted_score(hard_correct) > _weighted_score(easy_correct)


def test_empty():
    assert _weighted_score([]) == 0.0


def test_answered_none_counts_as_wrong():
    answers = [FakeAnswer(1, None), FakeAnswer(1, True)]
    assert _weighted_score(answers) == 0.5