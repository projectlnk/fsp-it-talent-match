"""Модели тестирования, категорий и кулдаунов смены грейда."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class QuestionType(str, enum.Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TEXT = "text"
    CODE = "code"


class AttemptStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class CategoryStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    NOT_CONFIRMED = "not_confirmed"


class Specialization(Base):
    __tablename__ = "specializations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    order: Mapped[int] = mapped_column(Integer)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("specialization_id", "grade_id", name="uq_categories_spec_grade"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="CASCADE")
    )
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="CASCADE"))

    specialization: Mapped[Specialization] = relationship()
    grade: Mapped[Grade] = relationship()


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    specialization_id: Mapped[int] = mapped_column(ForeignKey("specializations.id", ondelete="CASCADE"))
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="CASCADE"))
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[QuestionType] = mapped_column(Enum(QuestionType, name="question_type"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correct_answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    specialization_id: Mapped[int] = mapped_column(ForeignKey("specializations.id"))
    declared_grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    target_grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"))
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, name="attempt_status"), default=AttemptStatus.IN_PROGRESS
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    answers: Mapped[list["TestAnswer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class TestAnswer(Base):
    __tablename__ = "test_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("test_attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    # Снапшот конкретного вопроса: текст, варианты, правильный ответ.
    # Заполняется при старте попытки. Правильный ответ здесь лежит только
    # для серверной проверки — в API наружу не отдаётся.
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Ответ кандидата. Пусто до того, как он ответит.
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attempt: Mapped[TestAttempt] = relationship(back_populates="answers")


class CandidateCategory(Base):
    __tablename__ = "candidate_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    status: Mapped[CategoryStatus] = mapped_column(
        Enum(CategoryStatus, name="category_status"), default=CategoryStatus.PENDING
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship()


class GradeChangeCooldown(Base):
    __tablename__ = "grade_change_cooldowns"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), unique=True
    )
    last_change_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))