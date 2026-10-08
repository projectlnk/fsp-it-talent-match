"""Инстанцирование шаблонов вопросов в конкретные задания.

Шаблон (Question) хранит текст с плейсхолдерами и список допустимых
значений переменных. При старте попытки инстанцировщик подставляет
случайные значения и получает конкретный вопрос.

Так решается задача антиутечки: даже если кандидат поделится скриншотом,
в следующей попытке значения будут другими. Сложность при этом не меняется,
потому что структура шаблона фиксирована.
"""
from __future__ import annotations

import random
from typing import Any

from app.modules.assessments.models import Question


def instantiate_question(question: Question, rng: random.Random) -> dict[str, Any]:
    """Превращает шаблон в конкретный вопрос.

    Возвращает словарь:
      {
        "question_id": int,
        "topic": str | None,
        "difficulty": int,
        "type": str,
        "text": str,
        "options": list[str],
        "correct": Any,          # правильный ответ (наружу не отдаётся)
        "variables": dict,       # выбранные значения переменных
      }
    """
    payload = question.payload or {}
    text_template: str = payload.get("text_template") or payload.get("text") or ""
    variables: dict[str, list[dict[str, Any]]] = payload.get("variables") or {}
    options: list[str] = list(payload.get("options") or [])

    chosen: dict[str, str] = {}
    correct: Any = None

    for name, values in variables.items():
        if not values:
            continue
        pick = rng.choice(values)
        chosen[name] = pick.get("value", "")
        correct = pick.get("answer")

    text = text_template.format(**chosen) if chosen else text_template

    # Если у вопроса нет variables — это fixed-вопрос.
    # Правильный ответ берём из Question.correct_answer.
    if not variables:
        raw = getattr(question, "correct_answer", None)
        if isinstance(raw, dict):
            correct = raw.get("value")
        else:
            correct = raw

    shuffled = list(options)
    rng.shuffle(shuffled)

    return {
        "question_id": question.id,
        "topic": question.topic,
        "difficulty": question.difficulty,
        "type": payload.get("type", question.type.value if hasattr(question.type, "value") else str(question.type)),
        "text": text,
        "options": shuffled,
        "correct": correct,
        "variables": chosen,
    }


def public_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Убирает из снапшота правильный ответ и служебные поля.

    Эту функцию вызывают перед отдачей вопроса клиенту, чтобы правильный
    ответ не утёк в браузер или в логи.
    """
    return {
        "question_id": snapshot.get("question_id"),
        "text": snapshot.get("text"),
        "options": snapshot.get("options", []),
        "type": snapshot.get("type", "single_choice"),
    }


def is_correct(snapshot: dict[str, Any], answer: dict[str, Any]) -> bool:
    """Сверяет ответ кандидата с правильным из снапшота.

    answer ожидается в виде {"value": "..."} для single_choice или
    {"values": ["...", "..."]} для multiple_choice.
    """
    correct = snapshot.get("correct")
    if correct is None:
        return False

    qtype = snapshot.get("type", "single_choice")

    if qtype == "multiple_choice":
        correct_set = set(correct) if isinstance(correct, list) else {correct}
        given = set(answer.get("values") or [])
        return given == correct_set

    # single_choice и всё остальное — сравнение по значению
    return answer.get("value") == correct