"""Transactional rules shared by HTML, scheduled processing and demo tools."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from app.core.config import get_settings
from app.modules.auth.models import User, UserRole
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import EmployerProfile, Offer, OfferStatus
from app.modules.assessments.models import Specialization
from app.modules.matching.schemas import CandidateSearchQuery
from app.modules.matching import service as matching, queries
from app.modules.matching.ranking import rank_candidate
from app.modules.career.models import Opportunity, Application, ActivityEvent, Meeting, ThreadMessage, PrivacyConsent, DemoClock
from app.modules.career.schemas import OpportunityInput, MeetingInput


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now(session):
    instant = datetime.now(UTC)
    if get_settings().demo_mode:
        clock = session.get(DemoClock, 1)
        if clock:
            instant += timedelta(days=clock.offset_days)
    return instant


def fail(message, code=409):
    raise HTTPException(code, message)


def employer(session, user_id):
    row = session.scalar(select(EmployerProfile).where(EmployerProfile.user_id == user_id))
    if not row:
        fail('Компания не найдена', 404)
    return row


def candidate(session, user_id):
    row = session.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
    if not row:
        fail('Профиль не найден', 404)
    return row


def consent(session, user_id, kind, accepted):
    # User row serializes concurrent upserts without relying on browser state.
    session.scalar(select(User).where(User.id == user_id).with_for_update())
    row = session.scalar(select(PrivacyConsent).where(PrivacyConsent.user_id == user_id, PrivacyConsent.kind == kind))
    if row is None:
        row = PrivacyConsent(user_id=user_id, kind=kind)
        session.add(row)
    row.accepted = accepted
    row.recorded_at = datetime.now(UTC)  # Legal/security timestamp never uses demo clock.
    session.flush()
    return row


def require_processing(session, user_id):
    row = session.scalar(select(PrivacyConsent).where(PrivacyConsent.user_id == user_id, PrivacyConsent.kind == 'processing', PrivacyConsent.accepted.is_(True)))
    if not row:
        fail('Подтвердите согласие на обработку данных в настройках профиля', 403)


def owner(session, user_id, oid):
    company = employer(session, user_id)
    row = session.scalar(select(Opportunity).where(Opportunity.id == oid, Opportunity.employer_id == company.id).with_for_update())
    if not row:
        fail('Потребность или вакансия не найдена', 404)
    return row


def skill_list(value):
    return sorted(set(s.strip().lower() for s in value.split(',') if s.strip()))


def fingerprint(payload):
    # Similarity limited to normalized role + specialization + grade, not all company vacancies.
    title = ' '.join(payload.title.lower().split())
    return sha256(f'{title}|{payload.specialization}|{payload.grade}'.encode()).hexdigest()


def save_opportunity(session, user_id, kind, payload: OpportunityInput, oid=None):
    company = employer(session, user_id)
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == company.id).with_for_update())
    if not session.scalar(select(Specialization.id).where(Specialization.code == payload.specialization)):
        fail('Выберите существующую специализацию', 422)
    instant = now(session)
    row = owner(session, user_id, oid) if oid else None
    settings = get_settings()
    if row and row.status == 'deleted':
        fail('Удалённая запись доступна только в архиве')
    if row and instant >= utc(row.created_at) + timedelta(days=settings.vacancy_edit_days):
        for key in ('title', 'specialization', 'grade', 'skills', 'work_format'):
            old = getattr(row, key)
            new = getattr(payload, key)
            if key == 'skills':
                old, new = skill_list(old), skill_list(new)
            if old != new:
                fail('Первоначальный период изменения существенных требований завершён')
    if row is None:
        fp = fingerprint(payload)
        blocked = session.scalar(select(Opportunity.id).where(Opportunity.employer_id == company.id,
            Opportunity.kind == kind, Opportunity.fingerprint == fp, Opportunity.status == 'deleted',
            Opportunity.deleted_at > instant - timedelta(days=settings.vacancy_repost_days)))
        if blocked:
            fail('Аналогичную удалённую запись нельзя размещать повторно в течение 30 дней')
        row = Opportunity(employer_id=company.id, kind=kind, status='new', created_at=instant,
                          expires_at=instant + timedelta(days=settings.vacancy_lifetime_days), fingerprint=fp)
        session.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, ', '.join(skill_list(value)) if key == 'skills' else value)
    row.fingerprint = fingerprint(payload)
    session.flush()
    return row


def event(session, company_id, key, kind, points, explanation):
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == company_id).with_for_update())
    if session.scalar(select(ActivityEvent.id).where(ActivityEvent.employer_id == company_id, ActivityEvent.event_key == key)):
        return False
    session.add(ActivityEvent(employer_id=company_id, event_key=key, kind=kind, points=points,
                              explanation=explanation, created_at=now(session)))
    session.flush()
    return True


def vacancy_activity(session, oid):
    return session.scalar(select(func.count(Application.id)).where(Application.opportunity_id == oid,
        Application.status.in_(['accepted', 'rejected']))) or 0


def change_opportunity(session, user_id, oid, action):
    row = owner(session, user_id, oid)
    instant = now(session)
    if action == 'delete':
        if row.status != 'deleted':
            row.status, row.deleted_at = 'deleted', instant
    elif action == 'close':
        if row.status == 'deleted':
            fail('Удалённую запись нельзя восстановить')
        row.status = 'inactive'
    elif action in ('extend', 'restore'):
        if row.status == 'deleted':
            fail('Удалённая запись остаётся в архиве')
        if instant >= utc(row.created_at) + timedelta(days=get_settings().vacancy_edit_days):
            if vacancy_activity(session, row.id) < get_settings().vacancy_activity_threshold:
                fail('Недостаточно обработанных откликов для продления; порог: ' + str(get_settings().vacancy_activity_threshold))
        row.expires_at = max(instant, utc(row.expires_at)) + timedelta(days=get_settings().vacancy_lifetime_days)
        row.status = 'new' if instant < utc(row.created_at) + timedelta(days=get_settings().vacancy_edit_days) else 'stable'
    else:
        fail('Неизвестное действие', 422)
    session.flush()
    return row


def recommendations(session, opportunity, page=1, page_size=20):
    filters = CandidateSearchQuery(specialization=opportunity.specialization, grade=opportunity.grade,
                                   work_format=opportunity.work_format)
    requested = skill_list(opportunity.skills)
    rows = session.execute(queries.visible_candidates(filters).options(selectinload(CandidateProfile.skills),
                         selectinload(CandidateProfile.fsp_achievements))).all()
    result = []
    seen = set()
    for profile, category, spec, grade in rows:
        if profile.id in seen:
            continue
        seen.add(profile.id)
        card = matching._card((profile, category, spec, grade), CandidateSearchQuery(skills=requested))
        result.append({'card':card, **rank_profile(session,profile,opportunity,category.test_score,card.match_reasons)})
    result.sort(key=lambda item: (-item['score'], item['card'].profile_id))
    start = (page - 1) * page_size
    return result[start:start + page_size], len(result)

def rank_profile(session, profile, opportunity, test_score, reasons):
    requested = skill_list(opportunity.skills)
    declared = {skill.skill.strip().lower() for skill in profile.skills}
    matched = len(set(requested) & declared)
    rank = rank_candidate(profile, specialization_code=opportunity.specialization, test_score=test_score, today=now(session).date())
    skill_points = 20 * matched / len(requested) if requested else 0
    return {'score':round(rank.score+skill_points,2), 'reasons':list(reasons)+rank.reasons+
        [f'Заявленные навыки запроса: {matched} из {len(requested)}; {skill_points:.1f} балла']}

def applicant_rank(session, profile, opportunity):
    from app.modules.assessments.models import CandidateCategory, Category, CategoryStatus, Grade
    current=session.execute(select(CandidateCategory,Specialization,Grade).select_from(CandidateCategory)
        .join(Category,Category.id==CandidateCategory.category_id).join(Specialization,Specialization.id==Category.specialization_id)
        .join(Grade,Grade.id==Category.grade_id).where(CandidateCategory.candidate_profile_id==profile.id,CandidateCategory.is_current.is_(True))
        .order_by(CandidateCategory.id.desc()).limit(1)).first()
    matches=bool(current and current[0].status==CategoryStatus.CONFIRMED and current[1].code==opportunity.specialization and current[2].code==opportunity.grade)
    reasons=[f'Подтверждённая категория соответствует {opportunity.specialization}/{opportunity.grade}' if matches else 'Подтверждённая категория запроса отсутствует; самостоятельный отклик допускается']
    return {**rank_profile(session,profile,opportunity,current[0].test_score if matches else None,reasons),'category_match':matches}


def apply(session, user_id, oid, message):
    require_processing(session, user_id)
    profile = candidate(session, user_id)
    session.scalar(select(CandidateProfile).where(CandidateProfile.id == profile.id).with_for_update())
    job = session.scalar(select(Opportunity).where(Opportunity.id == oid).with_for_update())
    if not job or job.kind != 'vacancy' or job.status not in ('new', 'stable') or utc(job.expires_at) <= now(session):
        fail('Вакансия недоступна', 404)
    existing = session.scalar(select(Application).where(Application.opportunity_id == oid, Application.candidate_id == profile.id))
    if existing:
        return existing
    row = Application(opportunity_id=oid, candidate_id=profile.id, message=message, status='submitted', created_at=now(session))
    session.add(row)
    session.flush()
    return row


def decide(session, user_id, aid, decision):
    if decision not in ('accepted', 'rejected'):
        fail('Неверное решение', 422)
    company = employer(session, user_id)
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == company.id).with_for_update())
    application = session.scalar(select(Application).join(Opportunity).where(Application.id == aid,
        Opportunity.employer_id == company.id).with_for_update(of=Application))
    if not application:
        fail('Отклик не найден', 404)
    if application.status != 'submitted':
        if application.status == decision:
            return application
        fail('Решение уже принято')
    application.status, application.decided_at = decision, now(session)
    # One rewarded decision per company/candidate prevents reposting/farming one candidate.
    event(session, company.id, f'decision:{application.candidate_id}', 'decision', 2, 'Первое содержательное решение по отклику кандидата')
    session.flush()
    return application


def contact_allowed(session, candidate_id):
    profile = session.get(CandidateProfile, candidate_id)
    person = session.get(User, profile.user_id) if profile else None
    if not person or not person.is_active or person.role != UserRole.CANDIDATE:
        return False
    current = session.scalar(select(PrivacyConsent).where(PrivacyConsent.user_id==person.id,PrivacyConsent.kind=='processing'))
    # Existing accepted offers retain their contract unless the candidate explicitly revokes.
    return current is None or current.accepted

def permitted_pair(session, employer_id, candidate_id):
    if not contact_allowed(session,candidate_id):
        return False
    accepted_offer = session.scalar(select(Offer.id).where(Offer.employer_profile_id == employer_id,
        Offer.candidate_profile_id == candidate_id, Offer.status == OfferStatus.ACCEPTED))
    application = session.scalar(select(Application.id).join(Opportunity).where(Opportunity.employer_id == employer_id,
        Application.candidate_id == candidate_id))
    return bool(accepted_offer or application)


def pair_access(session, user, employer_id, candidate_id):
    e = session.get(EmployerProfile, employer_id)
    c = session.get(CandidateProfile, candidate_id)
    if not e or not c or user.id not in (e.user_id, c.user_id) or not permitted_pair(session, employer_id, candidate_id):
        fail('Взаимодействие недоступно', 404)
    return e, c


def meetings_for(session, user):
    model = EmployerProfile if user.role == UserRole.EMPLOYER else CandidateProfile
    profile = session.scalar(select(model).where(model.user_id == user.id))
    if not profile:
        return []
    field = Meeting.employer_id if user.role == UserRole.EMPLOYER else Meeting.candidate_id
    return list(session.scalars(select(Meeting).where(field == profile.id).order_by(Meeting.scheduled_at.desc())))


def schedule(session, user_id, cid, data: MeetingInput):
    company = employer(session, user_id)
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == company.id).with_for_update())
    if not permitted_pair(session, company.id, cid):
        fail('Сначала требуется принятое приглашение или самостоятельный отклик', 403)
    scheduled = data.scheduled_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=ZoneInfo(data.timezone))
    scheduled = utc(scheduled)
    if scheduled <= now(session):
        fail('Встреча должна быть в будущем', 422)
    existing = session.scalar(select(Meeting).where(Meeting.employer_id == company.id,
        Meeting.candidate_id == cid, Meeting.status == 'scheduled'))
    if existing:
        fail('Уже есть назначенная встреча с этим кандидатом')
    row = Meeting(employer_id=company.id, candidate_id=cid, scheduled_at=scheduled, timezone=data.timezone,
                  channel=data.channel, status='scheduled')
    session.add(row)
    session.flush()
    return row


def meeting_action(session, user, mid, action):
    existing = session.get(Meeting, mid)
    if not existing:
        fail('Встреча не найдена', 404)
    pair_access(session, user, existing.employer_id, existing.candidate_id)
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == existing.employer_id).with_for_update())
    row = session.scalar(select(Meeting).where(Meeting.id == mid).with_for_update())
    if not row:
        fail('Встреча не найдена', 404)
    company, profile = pair_access(session, user, row.employer_id, row.candidate_id)
    instant = now(session)
    if instant < utc(row.scheduled_at):
        fail('Встреча ещё не состоялась')
    is_candidate = user.id == profile.user_id
    if action == 'object' and is_candidate:
        if row.interview_confirmed_at:
            fail('Срок возражения завершён')
        row.candidate_objection_at = instant
        row.status = 'disputed'
    elif action == 'interview':
        if row.candidate_objection_at:
            fail('Кандидат оспорил встречу')
        if row.interview_confirmed_at:
            return row
        if is_candidate:
            row.interview_confirmed_at, row.status = row.interview_confirmed_at or instant, 'confirmed'
            event(session, company.id, f'interview:{profile.id}', 'interview', 10, 'Собеседование подтверждено кандидатом')
        else:
            row.employer_confirmed_at = row.employer_confirmed_at or instant
    elif action == 'hire':
        if not row.interview_confirmed_at or row.candidate_objection_at:
            fail('Сначала подтвердите собеседование')
        if is_candidate:
            row.candidate_hire_at = row.candidate_hire_at or instant
        else:
            row.employer_hire_at = row.employer_hire_at or instant
        if row.candidate_hire_at and row.employer_hire_at:
            row.status = 'hired'
            event(session, company.id, f'hire:{profile.id}', 'hire', 30, 'Обе стороны подтвердили найм')
    else:
        fail('Действие недоступно', 403)
    session.flush()
    return row


def send_message(session, user, eid, cid, body):
    pair_access(session, user, eid, cid)
    text = body.strip()
    if not text or len(text) > 2000:
        fail('Сообщение должно содержать от 1 до 2000 символов', 422)
    row = ThreadMessage(employer_id=eid, candidate_id=cid, author_id=user.id, body=text, created_at=now(session))
    session.add(row)
    session.flush()
    authors = set(session.scalars(select(ThreadMessage.author_id).where(ThreadMessage.employer_id == eid, ThreadMessage.candidate_id == cid)))
    if len(authors) == 2:
        event(session, eid, f'interaction:{cid}', 'interaction', 3, 'Обе стороны начали согласованное общение')
    return row


def process_due(session):
    instant, settings, changes = now(session), get_settings(), []
    # Consistent company -> workflow row lock order across all writers.
    list(session.scalars(select(EmployerProfile).order_by(EmployerProfile.id).with_for_update()))
    for job in session.scalars(select(Opportunity).where(Opportunity.status.in_(['new', 'stable'])).with_for_update()):
        old = job.status
        reason = ''
        if utc(job.expires_at) <= instant:
            job.status, reason = 'inactive', 'Срок публикации истёк'
        elif utc(job.created_at) + timedelta(days=settings.vacancy_edit_days) <= instant:
            job.status, reason = 'stable', 'Период изменения существенных требований завершён'
        if old != job.status:
            changes.append({'url':f'/career/opportunities/{job.id}', 'id':job.id, 'old':old, 'new':job.status, 'reason':reason})
    for meeting in session.scalars(select(Meeting).where(Meeting.status == 'scheduled').with_for_update()):
        if (meeting.employer_confirmed_at and not meeting.candidate_objection_at and
                max(utc(meeting.scheduled_at), utc(meeting.employer_confirmed_at)) + timedelta(days=settings.interview_auto_days) <= instant):
            meeting.status, meeting.interview_confirmed_at = 'confirmed', instant
            event(session, meeting.employer_id, f'interview:{meeting.candidate_id}', 'interview', 10,
                  'Работодатель подтвердил встречу; два дня без возражения кандидата')
            changes.append({'url':'/career/meetings', 'id':meeting.id, 'old':'scheduled', 'new':'confirmed', 'reason':'Два дня после встречи и заявления работодателя без возражения'})
    session.flush()
    return changes


def leaderboard(session):
    results = []
    for company in session.scalars(select(EmployerProfile).join(User).where(User.is_active.is_(True), User.role == UserRole.EMPLOYER)):
        complete = all((company.company_name, company.description, company.industry, company.contact_email or company.contact_phone))
        if complete:
            event(session, company.id, 'profile', 'profile', 5, 'Компания заполнила название, описание, отрасль и контакт')
        total = session.scalar(select(func.count(Application.id)).join(Opportunity).where(Opportunity.employer_id == company.id)) or 0
        handled = session.scalar(select(func.count(Application.id)).join(Opportunity).where(Opportunity.employer_id == company.id, Application.status != 'submitted')) or 0
        events = list(session.scalars(select(ActivityEvent).where(ActivityEvent.employer_id == company.id).order_by(ActivityEvent.id)))
        # Volume rewards capped; ratio counts only for three distinct candidate applications.
        unique_candidates = session.scalar(select(func.count(func.distinct(Application.candidate_id))).join(Opportunity).where(Opportunity.employer_id == company.id)) or 0
        ratio = round(10 * handled / total, 2) if unique_candidates >= 3 else 0
        event_points = sum(e.points for e in events if e.kind != 'decision') + min(20, sum(e.points for e in events if e.kind == 'decision'))
        results.append({'company':company, 'events':events, 'handled':handled, 'total':total,
                        'ratio_points':ratio, 'score':event_points + ratio})
    results.sort(key=lambda r:(-r['score'], r['company'].id))
    for position, row in enumerate(results, 1):
        row['position'] = position
    return results
