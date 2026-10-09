"""Bounded SQL pagination; EXISTS filters cannot multiply candidate rows."""
from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased, selectinload
from app.modules.auth.models import User, UserRole
from app.modules.assessments.models import CandidateCategory, Category, CategoryStatus, Specialization, Grade
from app.modules.candidates.models import CandidateProfile, CandidateSkill


def visible_candidates(filters):
    history = aliased(CandidateCategory)
    # A corrupted pair of current rows must not multiply results or resurrect
    # an older confirmed category after a newer failed category.
    latest = select(func.max(history.id)).where(
        history.candidate_profile_id == CandidateProfile.id,
        history.is_current.is_(True),
    ).correlate(CandidateProfile).scalar_subquery()
    stmt = (select(CandidateProfile, CandidateCategory, Specialization, Grade)
        .join(User, User.id == CandidateProfile.user_id)
        .join(CandidateCategory, CandidateCategory.id == latest)
        .join(Category, Category.id == CandidateCategory.category_id)
        .join(Specialization, Specialization.id == Category.specialization_id)
        .join(Grade, Grade.id == Category.grade_id)
        .where(CandidateProfile.is_searchable.is_(True), User.is_active.is_(True),
               User.role == UserRole.CANDIDATE,
               CandidateCategory.status == CategoryStatus.CONFIRMED))
    if filters.specialization:
        stmt = stmt.where(Specialization.code == filters.specialization)
    if filters.grade:
        stmt = stmt.where(Grade.code == filters.grade)
    if filters.skills:
        skill_name = func.lower(func.trim(CandidateSkill.skill))
        if filters.all_skills:
            for skill in filters.skills:
                stmt = stmt.where(exists(select(CandidateSkill.id).where(
                    CandidateSkill.candidate_profile_id == CandidateProfile.id,
                    skill_name == skill)))
        else:
            stmt = stmt.where(exists(select(CandidateSkill.id).where(
                CandidateSkill.candidate_profile_id == CandidateProfile.id,
                skill_name.in_(filters.skills))))
    if filters.location:
        escaped = filters.location.replace('!', '!!').replace('%', '!%').replace('_', '!_')
        stmt = stmt.where(CandidateProfile.location.ilike('%' + escaped + '%', escape='!'))
    if filters.work_format:
        stmt = stmt.where(CandidateProfile.work_format == filters.work_format)
    return stmt


def count_candidates(filters):
    return select(func.count()).select_from(visible_candidates(filters).with_only_columns(CandidateProfile.id).subquery())


def page_candidates(filters):
    return visible_candidates(filters).options(
        selectinload(CandidateProfile.skills), selectinload(CandidateProfile.fsp_achievements)
    ).order_by(func.lower(CandidateProfile.full_name), CandidateProfile.id).offset(
        (filters.page - 1) * filters.page_size).limit(filters.page_size)
