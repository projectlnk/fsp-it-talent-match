"""Shared search policy for API and HTML; contacts remain private at stage 6."""
import re
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.modules.assessments.models import Specialization, Grade, TestAttempt, AttemptStatus
from app.modules.candidates.models import CandidateProfile
from app.modules.matching import queries
from app.modules.matching.schemas import (CandidateSearchQuery, CandidateCardRead, CandidateDetailRead,
    CandidateSearchResult, SearchMeta, CandidateSkillBrief, CandidateExperienceBrief,
    FspAchievementBrief, TestResultBrief)

class MatchingError(Exception):
    pass
class CandidateNotFound(MatchingError):
    pass

# Free text can contain contacts even when structured fields are excluded.
_CONTACT = re.compile(r'(?:[\w.+-]+@[\w.-]+\.[\w-]+)|(?:https?://[^\s<>]+|www\.[^\s<>]+)|(?:@[\w.-]+)|(?:(?<!\w)\+?\d[\d ()-]{5,}\d(?!\w))', re.I)

def public_text(value):
    return _CONTACT.sub('[контакт скрыт]', value) if value else value


def _card(row, filters):
    profile, record, spec, grade = row
    skills = []
    seen_skills = set()
    for skill in sorted(profile.skills, key=lambda s: (s.skill.lower(), s.id)):
        normalized = skill.skill.strip().lower()
        if normalized not in seen_skills:
            seen_skills.add(normalized)
            skills.append(CandidateSkillBrief(skill=public_text(skill.skill), level=public_text(skill.level)))
    matched = list(dict.fromkeys(s.skill.strip().lower() for s in skills if s.skill.strip().lower() in filters.skills))
    reasons = [f'Подтверждённая категория: {public_text(spec.name)} / {public_text(grade.name)}']
    if matched:
        label = 'Совпали все запрошенные навыки: ' if filters.all_skills else 'Совпавшие навыки: '
        reasons.append(label + ', '.join(matched))
    if record.test_score is not None:
        reasons.append(f'Результат подтверждения категории: {record.test_score}%')
    return CandidateCardRead(profile_id=profile.id, full_name=public_text(profile.full_name),
        location=public_text(profile.location), desired_role=public_text(profile.desired_role),
        desired_salary_from=profile.desired_salary_from, desired_salary_to=profile.desired_salary_to,
        work_format=profile.work_format, experience_years=profile.experience_years,
        specialization_code=public_text(spec.code), specialization_name=public_text(spec.name),
        grade_code=public_text(grade.code), grade_name=public_text(grade.name),
        category_status=record.status.value, confirmed_at=record.confirmed_at,
        test_score=record.test_score, skills=skills, matched_skills=matched, match_reasons=reasons,
        fsp_has_achievements=bool(profile.fsp_achievements))


def search_candidates(session, query):
    total = session.scalar(queries.count_candidates(query)) or 0
    rows = session.execute(queries.page_candidates(query)).all()
    return CandidateSearchResult(items=[_card(row, query) for row in rows],
        meta=SearchMeta(total=total, page=query.page, page_size=query.page_size,
                        total_pages=(total + query.page_size - 1) // query.page_size))


def get_candidate_card(session, *, profile_id):
    query = CandidateSearchQuery()
    row = session.execute(queries.visible_candidates(query).where(CandidateProfile.id == profile_id).options(
        selectinload(CandidateProfile.skills), selectinload(CandidateProfile.experiences),
        selectinload(CandidateProfile.fsp_achievements))).first()
    if row is None:
        raise CandidateNotFound('Кандидат не найден')
    profile = row[0]
    results = session.execute(select(TestAttempt, Specialization, Grade)
        .join(Specialization, Specialization.id == TestAttempt.specialization_id)
        .join(Grade, Grade.id == TestAttempt.target_grade_id)
        .where(TestAttempt.candidate_profile_id == profile_id, TestAttempt.status == AttemptStatus.COMPLETED)
        .order_by(TestAttempt.finished_at.desc(), TestAttempt.id.desc()).limit(20)).all()
    experiences = [CandidateExperienceBrief(company_name=public_text(e.company_name), position=public_text(e.position),
        started_at=e.started_at, ended_at=e.ended_at, is_current=e.is_current, description=public_text(e.description))
        for e in sorted(profile.experiences, key=lambda e: (not e.is_current, -(e.started_at.toordinal() if e.started_at else 0), -e.id))]
    achievements = [FspAchievementBrief(title=public_text(a.title), discipline_code=public_text(a.discipline_code),
        competition_name=public_text(a.competition_name), competition_date=a.competition_date, place=a.place,
        rank=public_text(a.rank), is_team=a.is_team, is_demo=a.is_demo)
        for a in sorted(profile.fsp_achievements, key=lambda a: (a.competition_date.toordinal() if a.competition_date else 0, a.id), reverse=True)]
    return CandidateDetailRead(**_card(row, query).model_dump(), about=public_text(profile.about),
        experiences=experiences, fsp_achievements=achievements,
        results=[TestResultBrief(specialization_code=public_text(s.code), specialization_name=public_text(s.name),
            grade_code=public_text(g.code), grade_name=public_text(g.name), score=a.score, passed=a.passed,
            finished_at=a.finished_at) for a,s,g in results])


def reference_filters(session):
    return {'specializations': session.scalars(select(Specialization).order_by(Specialization.name)).all(),
            'grades': session.scalars(select(Grade).order_by(Grade.order, Grade.id)).all()}


def set_publication(session, user_id, is_searchable):
    from app.modules.career.service import consent, require_processing
    from app.modules.auth.models import User
    if is_searchable:
        user = session.get(User, user_id)
        if not user or not user.is_email_verified:
            from fastapi import HTTPException
            raise HTTPException(403, 'Сначала подтвердите email')
        require_processing(session, user_id)
    session.scalar(select(User).where(User.id == user_id).with_for_update())
    profile = session.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id)
                             .with_for_update().execution_options(populate_existing=True))
    if profile is None:
        raise CandidateNotFound('Профиль не найден')
    profile.is_searchable = is_searchable
    consent(session, user_id, 'publication', is_searchable)
    session.commit()
    return profile.is_searchable


def get_publication(session, user_id):
    value = session.scalar(select(CandidateProfile.is_searchable).where(CandidateProfile.user_id == user_id))
    if value is None:
        raise CandidateNotFound('Профиль не найден')
    return value
