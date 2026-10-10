"""Pydantic-схемы профиля кандидата."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from app.modules.candidates.models import WorkFormat
from app.modules.assessments.grades import GradeCode


# --- Навыки --------------------------------------------------------------


class CandidateSkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill: str
    level: str | None = None


class CandidateSkillCreate(BaseModel):
    @field_validator('level', mode='before')
    @classmethod
    def _optional_level(cls, value):
        return value.strip().lower() or None if isinstance(value, str) else value

    @field_validator('skill', mode="before")
    @classmethod
    def _required_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Поле не может быть пустым")
        return value.strip() if isinstance(value, str) else value

    skill: str = Field(min_length=1, max_length=100)
    level: GradeCode | None = None


class CandidateSkillUpdate(BaseModel):
    @field_validator('level', mode='before')
    @classmethod
    def _optional_level(cls, value):
        return value.strip().lower() or None if isinstance(value, str) else value

    @field_validator('skill', mode="before")
    @classmethod
    def _required_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Поле не может быть пустым")
        return value.strip() if isinstance(value, str) else value

    skill: str | None = Field(default=None, min_length=1, max_length=100)
    level: GradeCode | None = None


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
    @field_validator('company_name', 'position', mode="before")
    @classmethod
    def _required_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Поле не может быть пустым")
        return value.strip() if isinstance(value, str) else value

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
    @field_validator('company_name', 'position', 'is_current', mode="before")
    @classmethod
    def _required_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Поле не может быть пустым")
        return value.strip() if isinstance(value, str) else value

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
    @field_validator('full_name', mode="before")
    @classmethod
    def _required_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Поле не может быть пустым")
        return value.strip() if isinstance(value, str) else value

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

# --- FSP ID --------------------------------------------------------------


class FspLinkRequest(BaseModel):
    participant_id: str = Field(min_length=1, max_length=255)


class FspRegistryLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    registry_participant_id: str
    linked_at: datetime


class FspAchievementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_achievement_id: str
    title: str
    discipline_code: str | None = None
    competition_name: str | None = None
    competition_date: date | None = None
    place: int | None = None
    rank: str | None = None
    team_name: str | None = None
    is_team: bool
    is_demo: bool
    imported_at: datetime


class FspProfileRead(BaseModel):
    """Полное состояние связи с ФСП: связь + достижения."""

    link: FspRegistryLinkRead | None
    achievements: list[FspAchievementRead] = Field(default_factory=list)
    is_demo: bool = True

class FspParticipantRead(BaseModel):
    """Участник реестра ФСП — для выбора в UI."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    email: str


class FspImportResult(BaseModel):
    """Результат импорта достижений."""

    created: int
    updated: int

class FspAchievementImport(BaseModel):
    """Validate the demo registry contract before any database changes."""
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=255)
    participant_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    discipline_code: str | None = Field(None, max_length=100)
    competition_name: str | None = Field(None, max_length=255)
    competition_date: date | None = None
    place: int | None = None
    rank: str | None = Field(None, max_length=100)
    team_name: str | None = Field(None, max_length=255)
    is_team: bool = False
