"""Pydantic-схемы модуля assessments."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from app.modules.assessments.grades import GradeCode


class SpecializationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


class GradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    order: int


class CategoryRead(BaseModel):
    id: int
    status: str
    is_current: bool
    confirmed_at: datetime | None
    specialization: SpecializationRead
    grade: GradeRead


class CooldownRead(BaseModel):
    active: bool
    next_allowed_at: datetime | None
    days_left: int


class StartAttemptRequest(BaseModel):
    specialization: str = Field(min_length=1, max_length=100)
    grade: GradeCode


class AttemptSummary(BaseModel):
    attempt_id: int
    status: str
    score: int | None
    passed: bool | None
    started_at: datetime
    finished_at: datetime | None
    specialization: SpecializationRead
    grade: GradeRead


class AttemptStateResponse(BaseModel):
    attempt_id: int
    status: str
    score: int | None
    passed: bool | None
    started_at: datetime
    finished_at: datetime | None
    total_questions: int
    answered_count: int
    questions: list[dict[str, Any]]


class SubmitAnswerRequest(BaseModel):
    value: str | None = None
    values: list[str] | None = None


class SubmitAnswerResponse(BaseModel):
    answer_id: int
    answered: bool