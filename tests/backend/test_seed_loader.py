"""Unit-тесты нормализации ключа шаблона."""
from __future__ import annotations

from app.modules.assessments.seed_loader import _normalize_text


def test_normalize_prefers_text_template():
    payload = {"text_template": "Hello {name}", "text": "Fallback"}
    assert _normalize_text(payload) == "Hello {name}"


def test_normalize_falls_back_to_text():
    payload = {"text": "Only text"}
    assert _normalize_text(payload) == "Only text"


def test_normalize_strips_whitespace():
    payload = {"text_template": "  spaced  "}
    assert _normalize_text(payload) == "spaced"


def test_normalize_empty_payload():
    assert _normalize_text({}) == ""