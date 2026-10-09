"""Модели профиля кандидата, опыта, навыков и достижений ФСП."""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkFormat(str, enum.Enum):
    OFFICE = "office"
    REMOTE = "remote"
    HYBRID = "hybrid"


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desired_salary_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desired_salary_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_format: Mapped[WorkFormat | None] = mapped_column(Enum(WorkFormat, name="work_format"), nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    skills: Mapped[list["CandidateSkill"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    experiences: Mapped[list["CandidateExperience"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    fsp_link: Mapped["FspRegistryLink | None"] = relationship(
        back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    fsp_achievements: Mapped[list["FspAchievement"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "skill", name="uq_candidate_skills_profile_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    skill: Mapped[str] = mapped_column(String(100))
    level: Mapped[str | None] = mapped_column(String(50), nullable=True)

    profile: Mapped[CandidateProfile] = relationship(back_populates="skills")


class CandidateExperience(Base):
    __tablename__ = "candidate_experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    company_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ended_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[CandidateProfile] = relationship(back_populates="experiences")


class FspRegistryLink(Base):
    __tablename__ = "fsp_registry_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), unique=True
    )
    registry_participant_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped[CandidateProfile] = relationship(back_populates="fsp_link")


class FspAchievement(Base):
    __tablename__ = "fsp_achievements"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_id",
            "external_achievement_id",
            name="uq_fsp_achievements_profile_external",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_profile_id: Mapped[int] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    external_achievement_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    discipline_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    competition_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    competition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank: Mapped[str | None] = mapped_column(String(100), nullable=True)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_team: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped[CandidateProfile] = relationship(back_populates="fsp_achievements")
