"""Unit-тесты вспомогательных функций сервиса кандидатов по ФСП."""
from __future__ import annotations

from datetime import date

from app.modules.candidates.service import _parse_iso_date


def test_parse_iso_date_none():
    assert _parse_iso_date(None) is None


def test_parse_iso_date_empty_string():
    assert _parse_iso_date("") is None


def test_parse_iso_date_string():
    assert _parse_iso_date("2024-09-15") == date(2024, 9, 15)


def test_parse_iso_date_invalid_string():
    assert _parse_iso_date("not-a-date") is None
    assert _parse_iso_date("2024-13-01") is None


def test_parse_iso_date_date_object():
    d = date(2024, 5, 10)
    assert _parse_iso_date(d) is d