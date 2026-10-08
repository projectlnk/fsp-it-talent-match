"""Unit-тесты логики ответов."""
from __future__ import annotations

from datetime import UTC, datetime

from app.modules.assessments.service import attempt_public_state
from app.modules.assessments.models import AttemptStatus


class FakeAnswer:
    def __init__(self, id_, snapshot, answer=None, is_correct=None, answered_at=None):
        self.id = id_
        self.question_snapshot = snapshot
        self.answer = answer
        self.is_correct = is_correct
        self.answered_at = answered_at


class FakeAttempt:
    def __init__(self, id_, status, answers, score=None, passed=None):
        self.id = id_
        self.status = status
        self.answers = answers
        self.score = score
        self.passed = passed
        self.started_at = datetime.now(UTC)
        self.finished_at = None


def _snapshot(qid=1):
    return {
        "question_id": qid,
        "text": "Вопрос?",
        "options": ["a", "b"],
        "type": "single_choice",
        "correct": "a",
    }


def test_public_state_hides_correct_while_in_progress():
    answers = [
        FakeAnswer(1, _snapshot(), answer={"value": "a"}, is_correct=True, answered_at=datetime.now(UTC)),
        FakeAnswer(2, _snapshot(), None, None, None),
    ]
    attempt = FakeAttempt(1, AttemptStatus.IN_PROGRESS, answers)
    state = attempt_public_state(attempt)
    assert state["answered_count"] == 1
    assert state["total_questions"] == 2
    for item in state["questions"]:
        assert "is_correct" not in item
        assert "correct" not in item["question"]


def test_public_state_shows_correct_after_completion():
    answers = [
        FakeAnswer(1, _snapshot(), answer={"value": "a"}, is_correct=True, answered_at=datetime.now(UTC)),
        FakeAnswer(2, _snapshot(), answer={"value": "b"}, is_correct=False, answered_at=datetime.now(UTC)),
    ]
    attempt = FakeAttempt(1, AttemptStatus.COMPLETED, answers, score=50, passed=False)
    state = attempt_public_state(attempt)
    assert state["status"] == "completed"
    assert state["questions"][0]["is_correct"] is True
    assert state["questions"][1]["is_correct"] is False