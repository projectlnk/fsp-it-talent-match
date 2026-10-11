"""Explicit employer-facing DTOs: never serialize a whole profile or user."""
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from app.modules.candidates.models import WorkFormat

class CandidateSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specialization: str | None = Field(None, max_length=100)
    grade: str | None = Field(None, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=20)
    all_skills: bool = False
    location: str | None = Field(None, max_length=255)
    work_format: WorkFormat | None = None
    query: str | None = Field(None, max_length=255)
    desired_role: str | None = Field(None, max_length=255)
    experience_min: int | None = Field(None, ge=0, le=80)
    experience_max: int | None = Field(None, ge=0, le=80)
    salary_min: int | None = Field(None, ge=0, le=2147483647)
    salary_max: int | None = Field(None, ge=0, le=2147483647)
    fsp: bool | None = None
    test_score_min: int | None = Field(None, ge=0, le=100)
    activity_min: int | None = Field(None, ge=0)
    page: int = Field(1, ge=1, le=100000)
    page_size: int = Field(20, ge=1, le=50)

    @field_validator('specialization', 'grade', 'location', 'query', 'desired_role', mode='before')
    @classmethod
    def clean_optional(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator('skills')
    @classmethod
    def clean_skills(cls, value):
        result = list(dict.fromkeys(s.strip().lower() for s in value if s.strip()))
        if any(len(s) > 100 for s in result):
            raise ValueError('Навык не должен превышать 100 символов')
        return result

    @model_validator(mode='after')
    def ranges(self):
        for low, high in [('experience_min','experience_max'),('salary_min','salary_max')]:
            if getattr(self,low) is not None and getattr(self,high) is not None and getattr(self,low) > getattr(self,high):
                raise ValueError('Нижняя граница не может превышать верхнюю')
        return self

class CandidateSkillBrief(BaseModel):
    skill: str
    level: str | None = None

class CandidateExperienceBrief(BaseModel):
    company_name: str
    position: str
    started_at: date | None = None
    ended_at: date | None = None
    is_current: bool
    description: str | None = None

class FspAchievementBrief(BaseModel):
    title: str
    discipline_code: str | None = None
    competition_name: str | None = None
    competition_date: date | None = None
    place: int | None = None
    rank: str | None = None
    is_team: bool
    is_demo: bool

class TestResultBrief(BaseModel):
    specialization_code: str
    specialization_name: str
    grade_code: str
    grade_name: str
    score: int | None
    passed: bool | None
    finished_at: datetime | None

class CandidateCardRead(BaseModel):
    photo_version: str | None = None
    profile_id: int
    full_name: str
    location: str | None = None
    desired_role: str | None = None
    desired_salary_from: int | None = None
    desired_salary_to: int | None = None
    work_format: WorkFormat | None = None
    experience_years: int | None = None
    specialization_code: str
    specialization_name: str
    grade_code: str
    grade_name: str
    category_status: str
    confirmed_at: datetime | None
    test_score: int | None
    matched_skills: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    skills: list[CandidateSkillBrief] = Field(default_factory=list)
    fsp_has_achievements: bool = False
    fsp_achievement_count: int = 0
    solved_tasks: int = 0

class CandidateDetailRead(CandidateCardRead):
    about: str | None = None
    experiences: list[CandidateExperienceBrief] = Field(default_factory=list)
    fsp_achievements: list[FspAchievementBrief] = Field(default_factory=list)
    results: list[TestResultBrief] = Field(default_factory=list)

class SearchMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int

class CandidateSearchResult(BaseModel):
    items: list[CandidateCardRead]
    meta: SearchMeta

class SearchPublication(BaseModel):
    is_searchable: bool


class TeamNeedPositionInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    filters: CandidateSearchQuery

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class TeamNeedInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    positions: list[TeamNeedPositionInput] = Field(min_length=1, max_length=10)

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


def search_query_from_params(params, prefix=''):
    """Same parsing/validation for ordinary GET searches and saved form filters."""
    optional = ('query', 'desired_role', 'experience_min', 'experience_max',
                'salary_min', 'salary_max', 'fsp', 'test_score_min', 'activity_min',
                'specialization', 'grade', 'location', 'work_format')
    values = {key: params.get(prefix + key) or None for key in optional}
    return CandidateSearchQuery(**values,
        skills=[s for value in params.getlist(prefix + 'skills') for s in value.split(',')],
        all_skills=params.get(prefix + 'all_skills', False),
        page=params.get(prefix + 'page') or 1, page_size=params.get(prefix + 'page_size') or 20)
