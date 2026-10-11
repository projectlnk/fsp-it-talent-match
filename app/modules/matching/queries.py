"""Bounded SQL pagination; EXISTS filters cannot multiply candidate rows."""
from sqlalchemy import exists, func, select, or_
from sqlalchemy.orm import aliased, selectinload
from app.modules.auth.models import User, UserRole
from app.modules.assessments.models import CandidateCategory, Category, CategoryStatus, Specialization, Grade, TestAttempt, TestAnswer, AttemptStatus
from app.modules.candidates.models import CandidateProfile, CandidateSkill, FspAchievement


def solved_tasks_count():
    # Completed tests only; repeated correct answers to the same task count once.
    return select(func.count(func.distinct(TestAnswer.question_id))).join(TestAttempt, TestAttempt.id == TestAnswer.test_attempt_id).where(
        TestAttempt.candidate_profile_id == CandidateProfile.id, TestAttempt.status == AttemptStatus.COMPLETED,
        TestAnswer.is_correct.is_(True)).correlate(CandidateProfile).scalar_subquery()


def achievements_count(real_only=False):
    stmt = select(func.count(FspAchievement.id)).where(FspAchievement.candidate_profile_id == CandidateProfile.id)
    if real_only:
        stmt = stmt.where(FspAchievement.is_demo.is_(False))
    return stmt.correlate(CandidateProfile).scalar_subquery()


def contains(column, value):
    escaped = value.replace('!', '!!').replace('%', '!%').replace('_', '!_')
    return column.ilike('%' + escaped + '%', escape='!')


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
    if filters.query:
        stmt = stmt.where(or_(contains(CandidateProfile.full_name,filters.query),contains(CandidateProfile.desired_role,filters.query),contains(CandidateProfile.about,filters.query)))
    if filters.desired_role:
        stmt = stmt.where(contains(CandidateProfile.desired_role,filters.desired_role))
    for key, column, is_min in [('experience_min',CandidateProfile.experience_years,True),('experience_max',CandidateProfile.experience_years,False),('salary_min',CandidateProfile.desired_salary_to,True),('salary_max',CandidateProfile.desired_salary_from,False),('test_score_min',CandidateCategory.test_score,True)]:
        value = getattr(filters,key)
        if value is not None:
            stmt = stmt.where(column >= value if is_min else column <= value)
    if filters.fsp is not None:
        stmt = stmt.where(achievements_count() > 0 if filters.fsp else achievements_count() == 0)
    if filters.activity_min is not None:
        stmt = stmt.where(solved_tasks_count() >= filters.activity_min)
    return stmt


def count_candidates(filters):
    return select(func.count()).select_from(visible_candidates(filters).with_only_columns(CandidateProfile.id).subquery())


def page_candidates(filters):
    matched = select(func.count(func.distinct(func.lower(func.trim(CandidateSkill.skill))))).where(
        CandidateSkill.candidate_profile_id == CandidateProfile.id,
        func.lower(func.trim(CandidateSkill.skill)).in_(filters.skills)).correlate(CandidateProfile).scalar_subquery()
    return visible_candidates(filters).options(
        selectinload(CandidateProfile.skills), selectinload(CandidateProfile.fsp_achievements)
    ).order_by(matched.desc(),func.coalesce(CandidateCategory.test_score,0).desc(),achievements_count(True).desc(),achievements_count().desc(),solved_tasks_count().desc(),func.lower(CandidateProfile.full_name), CandidateProfile.id).offset(
        (filters.page - 1) * filters.page_size).limit(filters.page_size)
