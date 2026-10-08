"""Unit-тесты инстанцировщика шаблонов вопросов."""
from __future__ import annotations

import random

import pytest

from app.modules.assessments.instantiate import (
    instantiate_question,
    is_correct,
    public_view,
)
from app.modules.assessments.models import QuestionType


class FakeQuestion:
    id = 1
    topic = "http"
    difficulty = 2
    type = QuestionType.SINGLE_CHOICE
    payload = {
        "type": "single_choice",
        "text_template": "Какой статус-код, если {scenario}?",
        "variables": {
            "scenario": [
                {"value": "ресурс не найден", "answer": "404"},
                {"value": "пользователь не авторизован", "answer": "401"},
            ]
        },
        "options": ["200", "401", "404", "500"],
    }


class FixedQuestion:
    id = 2
    topic = "basics"
    difficulty = 1
    type = QuestionType.SINGLE_CHOICE
    payload = {
        "type": "single_choice",
        "text": "Что такое HTTP?",
        "options": ["Протокол", "База данных", "Язык"],
    }


def test_instantiate_substitutes_variables():
    snapshot = instantiate_question(FakeQuestion, random.Random(1))
    assert snapshot["text"] in {
        "Какой статус-код, если ресурс не найден?",
        "Какой статус-код, если пользователь не авторизован?",
    }
    assert snapshot["correct"] in {"404", "401"}


def test_instantiate_shuffles_options():
    rng_a = random.Random(1)
    rng_b = random.Random(2)
    a = instantiate_question(FakeQuestion, rng_a)["options"]
    b = instantiate_question(FakeQuestion, rng_b)["options"]
    assert set(a) == set(b)
    # хотя бы раз порядок отличается
    assert a != b or instantiate_question(FakeQuestion, random.Random(3))["options"] != a


def test_public_view_hides_correct():
    snapshot = instantiate_question(FakeQuestion, random.Random(1))
    public = public_view(snapshot)
    assert "correct" not in public
    assert "variables" not in public
    assert "options" in public
    assert "text" in public


def test_is_correct_returns_true_for_correct():
    snapshot = instantiate_question(FakeQuestion, random.Random(1))
    assert is_correct(snapshot, {"value": snapshot["correct"]}) is True


def test_is_correct_returns_false_for_wrong():
    snapshot = instantiate_question(FakeQuestion, random.Random(1))
    assert is_correct(snapshot, {"value": "__wrong__"}) is False


def test_is_correct_handles_missing_correct():
    snapshot = {"correct": None, "type": "single_choice"}
    assert is_correct(snapshot, {"value": "anything"}) is False


def test_multiple_choice():
    snapshot = {
        "type": "multiple_choice",
        "correct": ["a", "b"],
    }
    assert is_correct(snapshot, {"values": ["a", "b"]}) is True
    assert is_correct(snapshot, {"values": ["b", "a"]}) is True
    assert is_correct(snapshot, {"values": ["a"]}) is False
    assert is_correct(snapshot, {"values": ["a", "b", "c"]}) is False


def test_fixed_question_without_variables():
    snapshot = instantiate_question(FixedQuestion, random.Random(1))
    assert snapshot["text"] == "Что такое HTTP?"
    assert snapshot["correct"] is None  # у fixed вопроса нет answer в payload