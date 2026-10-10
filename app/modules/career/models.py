"""Additive hiring workflow; existing users, profiles and offers stay authoritative."""
from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Integer, DateTime, Boolean, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Opportunity(Base):
    __tablename__ = 'career_opportunities'
    __table_args__ = (CheckConstraint('salary_from >= 0 AND salary_to >= salary_from', name='career_salary_range'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey('employer_profiles.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    specialization: Mapped[str] = mapped_column(String(100))
    grade: Mapped[str] = mapped_column(String(50))
    skills: Mapped[str] = mapped_column(Text, default='')
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    work_format: Mapped[str] = mapped_column(String(20))
    contact_method: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default='new', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    demo_set: Mapped[str | None] = mapped_column(String(64), index=True)


class Application(Base):
    __tablename__ = 'job_applications'
    __table_args__ = (UniqueConstraint('opportunity_id', 'candidate_id', name='one_job_application'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey('career_opportunities.id'), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id'), index=True)
    message: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='submitted')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityEvent(Base):
    __tablename__ = 'employer_activity_events'
    __table_args__ = (UniqueConstraint('employer_id', 'event_key', name='unique_activity_event'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey('employer_profiles.id'), index=True)
    event_key: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(40))
    points: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Meeting(Base):
    __tablename__ = 'career_meetings'
    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey('employer_profiles.id'), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id'), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(25), default='scheduled')
    employer_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interview_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_objection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    employer_hire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_hire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_set: Mapped[str | None] = mapped_column(String(64), index=True)


class ThreadMessage(Base):
    __tablename__ = 'career_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey('employer_profiles.id'), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id'), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrivacyConsent(Base):
    __tablename__ = 'privacy_consents'
    __table_args__ = (UniqueConstraint('user_id', 'kind', name='one_current_consent'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    kind: Mapped[str] = mapped_column(String(25))
    accepted: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DemoClock(Base):
    __tablename__ = 'demo_clock'
    id: Mapped[int] = mapped_column(primary_key=True)
    offset_days: Mapped[int] = mapped_column(Integer, default=0)


class DemoSet(Base):
    __tablename__ = 'demo_sets'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    employer_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    candidate_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
