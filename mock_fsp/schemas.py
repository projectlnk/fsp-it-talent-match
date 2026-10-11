"""Схемы мока FSP ID.

Локальный контракт для демонстрации, не официальный API ФСП.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, ConfigDict


class Participant(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    display_name: str = Field(min_length=1, max_length=255)
    email: str = Field(max_length=255, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


class Achievement(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    participant_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    title: str = Field(min_length=1, max_length=255)
    discipline_code: str | None = None
    competition_name: str | None = None
    competition_date: date | None = None
    place: int | None = Field(None, ge=1)
    rank: str | None = None
    team_name: str | None = None
    is_team: bool = False
