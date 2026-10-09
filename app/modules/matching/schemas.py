"""Pydantic-схемы модуля поиска кандидатов."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CandidateSkillBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill: str
    level: str | None = None


class CandidateExperienceBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    position: str
    is_current: bool


class FspAchievementBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    discipline_code: str | None = None
    competition_name: str | None = None
    competition_date: datetime | None = None
    place: int | None = None
    rank: str | None = None
    is_team: bool
    is_demo: bool


class CandidateCardRead(BaseModel):
    """Карточка кандидата в результатах поиска.

    Не содержит контактных данных. ФИО и места работы показываются — это
    допустимо по Q&A. Телефон и email скрыты до принятия приглашения.
    """

    profile_id: int
    full_name: str
    location: str | None = None
    desired_role: str | None = None
    desired_salary_from: int | None = None
    desired_salary_to: int | None = None
    experience_years: int | None = None

    specialization_code: str
    specialization_name: str
    grade_code: str
    grade_name: str
    category_status: str

    test_score: int | None = None
    ranking_score: float
    ranking_reasons: list[str]

    skills: list[CandidateSkillBrief] = Field(default_factory=list)
    experiences: list[CandidateExperienceBrief] = Field(default_factory=list)
    fsp_achievements: list[FspAchievementBrief] = Field(default_factory=list)
    fsp_has_achievements: bool = False


class SearchMeta(BaseModel):
    total: int
    limit: int
    offset: int


class CandidateSearchResult(BaseModel):
    items: list[CandidateCardRead]
    meta: SearchMeta


class CandidateSearchQuery(BaseModel):
    """Параметры поиска, передаваемые в сервис.

    Все поля опциональны. Пустой запрос вернёт всех кандидатов с
    подтверждённой категорией.
    """

    specialization: str | None = None
    grade: str | None = None
    skills: list[str] = Field(default_factory=list)
    has_fsp_achievements: bool | None = None
    only_confirmed: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)