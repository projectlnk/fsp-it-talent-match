"""Pydantic-схемы профиля работодателя."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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