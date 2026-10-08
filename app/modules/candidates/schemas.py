"""Pydantic-схемы профиля кандидата."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.candidates.models import WorkFormat


# --- Навыки --------------------------------------------------------------


class CandidateSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill: str
    level: str | None = None


class CandidateSkillCreate(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    level: str | None = Field(default=None, max_length=50)


class CandidateSkillUpdate(BaseModel):
    skill: str | None = Field(default=None, min_length=1, max_length=100)
    level: str | None = Field(default=None, max_length=50)


# --- Опыт ----------------------------------------------------------------


class CandidateExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    position: str
    started_at: date | None = None
    ended_at: date | None = None
    description: str | None = None
    is_current: bool


class CandidateExperienceCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    position: str = Field(min_length=1, max_length=255)
    started_at: date | None = None
    ended_at: date | None = None
    description: str | None = None
    is_current: bool = False

    @model_validator(mode="after")
    def _check_dates(self) -> "CandidateExperienceCreate":
        if self.started_at and self.ended_at and self.started_at > self.ended_at:
            raise ValueError("started_at не может быть позже ended_at")
        return self


class CandidateExperienceUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    position: str | None = Field(default=None, min_length=1, max_length=255)
    started_at: date | None = None
    ended_at: date | None = None
    description: str | None = None
    is_current: bool | None = None


# --- Профиль -------------------------------------------------------------


class CandidateProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    full_name: str
    phone: str | None = None
    location: str | None = None
    about: str | None = None
    desired_role: str | None = None
    desired_salary_from: int | None = None
    desired_salary_to: int | None = None
    work_format: WorkFormat | None = None
    experience_years: int | None = None
    created_at: datetime
    updated_at: datetime
    skills: list[CandidateSkillRead] = Field(default_factory=list)
    experiences: list[CandidateExperienceRead] = Field(default_factory=list)


class CandidateProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    about: str | None = None
    desired_role: str | None = Field(default=None, max_length=255)
    desired_salary_from: int | None = Field(default=None, ge=0)
    desired_salary_to: int | None = Field(default=None, ge=0)
    work_format: WorkFormat | None = None
    experience_years: int | None = Field(default=None, ge=0, le=80)

    @model_validator(mode="after")
    def _check_salary(self) -> "CandidateProfileUpdate":
        low = self.desired_salary_from
        high = self.desired_salary_to
        if low is not None and high is not None and low > high:
            raise ValueError("desired_salary_from не может быть больше desired_salary_to")
        return self