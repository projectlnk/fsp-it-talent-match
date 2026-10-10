from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.modules.assessments.grades import GradeCode


class OpportunityInput(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=10, max_length=10000)
    specialization: str = Field(min_length=1, max_length=100)
    grade: GradeCode
    skills: str = Field(default='', max_length=2000)
    salary_from: int = Field(ge=0, le=2147483647)
    salary_to: int = Field(ge=0, le=2147483647)
    work_format: Literal['office', 'remote', 'hybrid']
    contact_method: str = Field(min_length=3, max_length=255)

    @field_validator('title', 'description', 'contact_method', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def salary(self):
        if self.salary_from > self.salary_to:
            raise ValueError('Зарплата от не может превышать зарплату до')
        return self


class MeetingInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    scheduled_at: datetime
    timezone: str = 'Europe/Moscow'
    channel: str = Field(min_length=3, max_length=255)

    @field_validator('timezone')
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError('Неизвестный часовой пояс')
        return value
