"""Схемы мока FSP ID.

Локальный контракт для демонстрации, не официальный API ФСП.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Participant(BaseModel):
    id: str
    display_name: str
    email: str


class Achievement(BaseModel):
    id: str
    participant_id: str
    title: str
    discipline_code: str | None = None
    competition_name: str | None = None
    competition_date: date | None = None
    place: int | None = None
    rank: str | None = None
    team_name: str | None = None
    is_team: bool = False