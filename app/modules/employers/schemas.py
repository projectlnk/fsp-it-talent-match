"""Pydantic-схемы профиля работодателя."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class EmployerProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    company_name: str
    description: str | None = None
    industry: str | None = None
    website: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    created_at: datetime
    updated_at: datetime


class EmployerProfileUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    industry: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)

# --- Приглашения ---------------------------------------------------------


class OfferCreate(BaseModel):
    """Создание приглашения конкретному кандидату.

    Привязка к вакансии не обязательна: адресное приглашение может
    существовать без опубликованной вакансии (по ТЗ).
    """

    candidate_profile_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    salary_from: int = Field(ge=0)
    salary_to: int = Field(ge=0)
    salary_gross: bool = True
    contact_method: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _check_salary(self) -> "OfferCreate":
        if self.salary_from > self.salary_to:
            raise ValueError("salary_from не может быть больше salary_to")
        return self


class OfferStatusUpdate(BaseModel):
    """Обновление статуса приглашения.

    Разрешённые значения: viewed, accepted, rejected. Переход в sent
    выполняет сервис при создании.
    """

    status: str = Field(pattern="^(viewed|accepted|rejected)$")


class EmployerProfileBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    industry: str | None = None


class CandidateBrief(BaseModel):
    """Публичный минимум о кандидате в карточке приглашения.

    Работодатель видит ФИО, специализацию и грейд, но не контакты,
    пока приглашение не принято.
    """

    profile_id: int
    full_name: str
    specialization_code: str | None = None
    specialization_name: str | None = None
    grade_code: str | None = None
    grade_name: str | None = None


class ContactsRead(BaseModel):
    """Контактные данные кандидата.

    Отдаются только после того, как кандидат принял приглашение
    (или откликнулся сам). Содержит email и телефон.
    """

    email: str | None = None
    phone: str | None = None


class OfferRead(BaseModel):
    """Полное представление приглашения для работодателя.

    Поле contacts заполняется только если status == accepted.
    """

    id: int
    status: str
    title: str
    description: str | None = None
    salary_from: int
    salary_to: int
    salary_currency: str
    salary_gross: bool
    contact_method: str | None = None
    created_at: datetime
    updated_at: datetime
    viewed_at: datetime | None = None
    responded_at: datetime | None = None

    employer: EmployerProfileBrief
    candidate: CandidateBrief
    contacts: ContactsRead | None = None