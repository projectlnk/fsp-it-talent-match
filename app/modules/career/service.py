"""Transactional rules shared by HTML, scheduled processing and demo tools."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
from sqlalchemy import select, func, case, cast, Float, and_, exists
from sqlalchemy.orm import selectinload, aliased
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


def normalized_activity(total, viewed):
    if not total:
        return 0.0
    if total >= 500:
        return round(min(100, 100 * viewed / (0.2 * total)), 2)
    if total >= 100:
        return float(min(100, viewed))
    if total >= 40 and viewed >= 40:
        return round(100 * viewed / total, 2)
    return float(viewed)


def vacancy_metrics(session, oid):
    total, viewed = session.execute(select(func.count(Application.id),
        func.count(Application.resume_viewed_at)).where(Application.opportunity_id == oid)).one()
    return {'total':total, 'viewed':viewed, 'activity':normalized_activity(total, viewed),
            'viewed_percent':round(100 * viewed / total, 1) if total else 0}


def vacancy_activity(session, oid):
    return vacancy_metrics(session, oid)['activity']


def vacancy_activity_order():
    # Correlated SQL calculation keeps ordering correct before pagination.
    total = select(func.count(Application.id)).where(Application.opportunity_id == Opportunity.id).correlate(Opportunity).scalar_subquery()
    viewed = select(func.count(Application.resume_viewed_at)).where(Application.opportunity_id == Opportunity.id).correlate(Opportunity).scalar_subquery()
    return case((total == 0, 0.0), (total >= 500, func.least(100.0, 500.0 * viewed / func.nullif(total, 0))),
        (total >= 100, cast(viewed, Float)), (and_(total >= 40, viewed >= 40), 100.0 * viewed / func.nullif(total, 0)),
        else_=cast(viewed, Float))


def vacancy_hired(session, oid):
    return bool(session.scalar(select(Meeting.id).where(Meeting.opportunity_id == oid,
        Meeting.status == 'hired', Meeting.employer_hire_at.is_not(None), Meeting.candidate_hire_at.is_not(None))))


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
        if vacancy_hired(session, row.id):
            fail('Вакансия успешно закрыта наймом; создайте новую запись для следующего подбора')
        if instant >= utc(row.created_at) + timedelta(days=get_settings().vacancy_edit_days):
            if vacancy_activity(session, row.id) < get_settings().vacancy_activity_threshold:
                fail('Недостаточная активность вакансии для продления; порог в процентах: ' + str(get_settings().vacancy_activity_threshold))
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
    application.resume_viewed_at = application.resume_viewed_at or now(session)
    event(session, company.id, f'decision:{application.candidate_id}', 'decision', 0, 'Решение по отклику; в общий рейтинг не входит')
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

def accepted_pair(session, employer_id, candidate_id):
    # A withdrawal closes the pair until a new invitation is explicitly accepted.
    # Pending/rejected offers do not override existing consent.
    latest = session.scalar(select(Offer.status).where(
        Offer.employer_profile_id == employer_id, Offer.candidate_profile_id == candidate_id,
        Offer.status.in_([OfferStatus.ACCEPTED, OfferStatus.REVOKED])).order_by(
        func.coalesce(Offer.revoked_at, Offer.responded_at, Offer.created_at).desc(), Offer.id.desc()).limit(1))
    return bool(contact_allowed(session, candidate_id) and latest == OfferStatus.ACCEPTED)


def permitted_pair(session, employer_id, candidate_id):
    if accepted_pair(session, employer_id, candidate_id):
        return True
    # Preserve access to history created under the old application-based rule.
    if not contact_allowed(session, candidate_id):
        return False
    return bool(session.scalar(select(ThreadMessage.id).where(ThreadMessage.employer_id == employer_id,
        ThreadMessage.candidate_id == candidate_id)) or session.scalar(select(Meeting.id).where(
        Meeting.employer_id == employer_id, Meeting.candidate_id == candidate_id)))


def can_view_candidate(session, employer_id, candidate_id):
    return bool(contact_allowed(session, candidate_id) and (accepted_pair(session, employer_id, candidate_id)
        or session.scalar(select(Application.id).join(Opportunity).where(
            Opportunity.employer_id == employer_id, Application.candidate_id == candidate_id))))


def invitation_messages(session, offer):
    company = session.get(EmployerProfile, offer.employer_profile_id)
    profile = session.get(CandidateProfile, offer.candidate_profile_id)
    instant = offer.responded_at or offer.created_at
    body = (f"{offer.title}\n{offer.description or ''}\n"
        f"Зарплата: {offer.salary_from}–{offer.salary_to} ₽ "
        f"({'до' if offer.salary_gross else 'после'} вычета НДФЛ).\n"
        f"Способ связи: {offer.contact_method or 'Не указан'}")
    for author, kind, text in [(company.user_id, 'invitation', body),
            (profile.user_id, 'acceptance', 'Приглашение принято. Готов обсудить предложенные условия')]:
        if not session.scalar(select(ThreadMessage.id).where(ThreadMessage.offer_id == offer.id, ThreadMessage.kind == kind)):
            session.add(ThreadMessage(employer_id=company.id, candidate_id=profile.id, author_id=author,
                body=text, kind=kind, offer_id=offer.id, created_at=instant))
    session.flush()


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
    if not accepted_pair(session, company.id, cid):
        fail('Сначала требуется принятое приглашение с условиями', 403)
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
    accepted = session.scalars(select(Offer).where(Offer.employer_profile_id == company.id,
        Offer.candidate_profile_id == cid, Offer.status == OfferStatus.ACCEPTED).order_by(Offer.responded_at.desc(), Offer.id.desc())).first()
    opportunity_id = getattr(data, 'opportunity_id', None)
    if opportunity_id is not None:
        if not session.scalar(select(Offer.id).where(Offer.employer_profile_id == company.id, Offer.candidate_profile_id == cid,
                Offer.status == OfferStatus.ACCEPTED, Offer.opportunity_id == opportunity_id)):
            fail('Нет принятого приглашения по выбранной вакансии', 403)
        if vacancy_hired(session, opportunity_id):
            fail('Вакансия уже закрыта наймом')
    elif accepted:
        opportunity_id = accepted.opportunity_id
    if opportunity_id and vacancy_hired(session, opportunity_id):
        fail('Вакансия уже закрыта наймом')
    row = Meeting(employer_id=company.id, candidate_id=cid, opportunity_id=opportunity_id, scheduled_at=scheduled, timezone=data.timezone,
                  channel=data.channel, status='scheduled')
    session.add(row)
    session.flush()
    event(session, company.id, f'meeting-scheduled:{row.id}', 'meeting_scheduled', 2, 'Назначена встреча')
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
    if row.status == 'cancelled':
        fail('Встреча отменена')
    if instant < utc(row.scheduled_at):
        fail('Встреча ещё не состоялась')
    is_candidate = user.id == profile.user_id
    if action == 'object' and is_candidate:
        if row.interview_confirmed_at:
            fail('Срок возражения завершён')
        row.candidate_objection_at = instant
        row.status = 'disputed'
        event(session, company.id, f'meeting-disputed:{row.id}', 'meeting_disputed', -2, 'Кандидат оспорил проведение встречи')
    elif action == 'interview':
        if row.candidate_objection_at:
            fail('Кандидат оспорил встречу')
        if row.interview_confirmed_at:
            return row
        if is_candidate:
            row.candidate_confirmed_at = row.candidate_confirmed_at or instant
        else:
            row.employer_confirmed_at = row.employer_confirmed_at or instant
        if row.candidate_confirmed_at and row.employer_confirmed_at:
            row.interview_confirmed_at, row.status = instant, 'confirmed'
            event(session, company.id, f'meeting-conducted:{row.id}', 'meeting_conducted', 8,
                'Проведение встречи подтверждено обеими сторонами; стоимость встречи стала 10 баллов')
    elif action == 'hire':
        if not row.interview_confirmed_at or row.candidate_objection_at:
            fail('Сначала подтвердите собеседование')
        if is_candidate:
            row.candidate_hire_at = row.candidate_hire_at or instant
        else:
            row.employer_hire_at = row.employer_hire_at or instant
        if row.candidate_hire_at and row.employer_hire_at:
            row.status = 'hired'
            event(session, company.id, f'hire:{profile.id}', 'hire', 0, 'Обе стороны явно подтвердили найм; отдельного бонуса нет')
            if row.opportunity_id:
                job = session.get(Opportunity, row.opportunity_id)
                if job and job.employer_id == company.id:
                    job.status = 'inactive'
    else:
        fail('Действие недоступно', 403)
    session.flush()
    return row


def send_message(session, user, eid, cid, body):
    pair_access(session, user, eid, cid)
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == eid).with_for_update())
    if not accepted_pair(session, eid, cid):
        fail('Для новых сообщений требуется принятое приглашение', 403)
    text = body.strip()
    if not text or len(text) > 2000:
        fail('Сообщение должно содержать от 1 до 2000 символов', 422)
    row = ThreadMessage(employer_id=eid, candidate_id=cid, author_id=user.id, body=text, kind='message', created_at=now(session))
    session.add(row)
    session.flush()
    if cid in rewarded_conversations(session, eid):
        event(session, eid, f'interaction-v2:{cid}', 'interaction_v2', 1,
            'Обе стороны отправили обычное сообщение после принятого приглашения')
    return row


def rewarded_conversations(session, eid):
    technical = aliased(ThreadMessage)
    invitation = aliased(ThreadMessage)
    accepted = exists(select(Offer.id).where(Offer.employer_profile_id == ThreadMessage.employer_id,
        Offer.candidate_profile_id == ThreadMessage.candidate_id,
        Offer.status.in_([OfferStatus.ACCEPTED, OfferStatus.REVOKED]),
        (Offer.revoked_at.is_(None) | (ThreadMessage.created_at <= Offer.revoked_at)),
        func.coalesce(Offer.responded_at, Offer.created_at) <= ThreadMessage.created_at,
        exists(select(technical.id).where(technical.offer_id == Offer.id, technical.kind == 'acceptance').correlate(Offer)),
        exists(select(invitation.id).where(invitation.offer_id == Offer.id, invitation.kind == 'invitation').correlate(Offer))))
    rows = session.execute(select(ThreadMessage.candidate_id, ThreadMessage.author_id).where(
        ThreadMessage.employer_id == eid, ThreadMessage.kind == 'message', accepted).distinct()).all()
    authors = {}
    for cid, uid in rows:
        authors.setdefault(cid, set()).add(uid)
    return {cid for cid, people in authors.items() if len(people) == 2}


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
            event(session, meeting.employer_id, f'meeting-conducted:{meeting.id}', 'meeting_conducted', 8,
                  'Работодатель подтвердил встречу; два дня без возражения кандидата')
            changes.append({'url':'/career/meetings', 'id':meeting.id, 'old':'scheduled', 'new':'confirmed', 'reason':'Два дня после встречи и заявления работодателя без возражения'})
    session.flush()
    return changes


def leaderboard(session):
    results = []
    for company in session.scalars(select(EmployerProfile).join(User).where(User.is_active.is_(True), User.role == UserRole.EMPLOYER)):
        meetings = list(session.scalars(select(Meeting).where(Meeting.employer_id == company.id)))
        conducted = sum(m.interview_confirmed_at is not None and not m.candidate_objection_at and m.status != 'cancelled' for m in meetings)
        scheduled = sum(m.interview_confirmed_at is None and m.status == 'scheduled' and not m.candidate_objection_at for m in meetings)
        closed = {m.opportunity_id for m in meetings if m.opportunity_id is not None and m.status == 'hired'
                  and m.employer_hire_at is not None and m.candidate_hire_at is not None}
        chats = len(rewarded_conversations(session, company.id))
        chat_limit = 10 + 5 * conducted
        chat_points = min(chats, chat_limit)
        raw_score = chat_points + 2 * scheduled + 10 * conducted
        score_limit = 200 + 100 * len(closed)
        vacancies = session.scalar(select(func.count(Opportunity.id)).where(Opportunity.employer_id == company.id,
            Opportunity.kind == 'vacancy', Opportunity.status.in_(['new','stable']), Opportunity.expires_at > now(session))) or 0
        total, viewed = session.execute(select(func.count(Application.id),func.count(Application.resume_viewed_at))
            .join(Opportunity).where(Opportunity.employer_id == company.id)).one()
        selected_ids = set(session.scalars(select(Application.candidate_id).join(Opportunity).where(Opportunity.employer_id == company.id, Application.status == 'accepted')))
        selected_ids.update(session.scalars(select(Offer.candidate_profile_id).where(Offer.employer_profile_id == company.id, Offer.status == OfferStatus.ACCEPTED)))
        results.append({'company':company, 'score':min(raw_score, score_limit), 'raw_score':raw_score,
            'chat_points':chat_points, 'chat_limit':chat_limit, 'chats':chats, 'score_limit':score_limit,
            'closed_vacancies':len(closed), 'vacancies':vacancies, 'meetings':scheduled,
            'interviews':conducted, 'hires':len(closed), 'total':total, 'viewed':viewed,
            'viewed_percent':round(100 * viewed / total, 1) if total else 0,
            'events':list(session.scalars(select(ActivityEvent).where(ActivityEvent.employer_id == company.id))),
            'handled':viewed, 'ratio_points':0, 'profile_points':0, 'selected':len(selected_ids)})
    results.sort(key=lambda r:(-r['score'], r['company'].id))
    for position, row in enumerate(results, 1):
        row['position'] = position
    return results


def opportunity_state(session, row):
    """Presentation of the existing lifecycle; does not change its transitions."""
    early = now(session) < utc(row.created_at) + timedelta(days=get_settings().vacancy_edit_days)
    enough = vacancy_activity(session, row.id) >= get_settings().vacancy_activity_threshold
    actions, reason = [], ''
    if vacancy_hired(session, row.id):
        reason = 'Успешно закрыта: найм явно подтверждён кандидатом и работодателем.'
    elif row.status == 'deleted':
        reason = 'Логически удалена. Данные и отклики сохранены; восстановление не разрешено действующими правилами.'
    else:
        if row.status in ('new', 'stable'):
            actions.append(('close', 'В архив'))
        if early or enough:
            actions.append(('restore', 'Восстановить') if row.status == 'inactive' else ('extend', 'Продлить'))
        else:
            reason = f'Для восстановления или продления достигните {get_settings().vacancy_activity_threshold}% активности этой записи.'
        actions.append(('delete', 'Удалить в архив'))
    return {'actions':actions, 'reason':reason, 'requirements_editable':early,
            'metrics':vacancy_metrics(session, row.id), 'hired':vacancy_hired(session, row.id),
            'edit_until':utc(row.created_at) + timedelta(days=get_settings().vacancy_edit_days)}


def connections_for(session, user):
    """Only pairs allowed by the original consent and participant policy."""
    if user.role == UserRole.EMPLOYER:
        eid = employer(session, user.id).id
        ids = set(session.scalars(select(Offer.candidate_profile_id).where(Offer.employer_profile_id == eid, Offer.status == OfferStatus.ACCEPTED)))
        ids.update(session.scalars(select(ThreadMessage.candidate_id).where(ThreadMessage.employer_id == eid)))
        ids.update(session.scalars(select(Meeting.candidate_id).where(Meeting.employer_id == eid)))
        return [(eid,c.id,c.full_name) for c in session.scalars(select(CandidateProfile).where(CandidateProfile.id.in_(ids)).order_by(CandidateProfile.full_name)) if permitted_pair(session,eid,c.id)]
    cid = candidate(session,user.id).id
    ids = set(session.scalars(select(Offer.employer_profile_id).where(Offer.candidate_profile_id == cid, Offer.status == OfferStatus.ACCEPTED)))
    ids.update(session.scalars(select(ThreadMessage.employer_id).where(ThreadMessage.candidate_id == cid)))
    ids.update(session.scalars(select(Meeting.employer_id).where(Meeting.candidate_id == cid)))
    return [(e.id,cid,e.company_name) for e in session.scalars(select(EmployerProfile).where(EmployerProfile.id.in_(ids))) if permitted_pair(session,e.id,cid)]


def record_resume_view(session, user, cid):
    if user.role != UserRole.EMPLOYER:
        fail('Недостаточно прав',403)
    company = employer(session,user.id)
    if not can_view_candidate(session, company.id, cid):
        fail('Данные кандидата недоступны', 404)
    # Zero points: unique viewed resumes are a metric, not a new reward.
    event(session,company.id,f'resume-view:{cid}','resume_view',0,'Просмотр резюме разрешённого кандидата; баллы не начисляются')
    return company.id


def update_meeting(session, user, mid, data=None, cancel=False):
    if user.role != UserRole.EMPLOYER:
        fail('Только работодатель может изменить или отменить встречу',403)
    existing = session.get(Meeting,mid)
    if not existing:
        fail('Встреча не найдена',404)
    pair_access(session,user,existing.employer_id,existing.candidate_id)
    session.scalar(select(EmployerProfile).where(EmployerProfile.id == existing.employer_id).with_for_update())
    row = session.scalar(select(Meeting).where(Meeting.id == mid).with_for_update().execution_options(populate_existing=True))
    if row.status != 'scheduled' or utc(row.scheduled_at) <= now(session) or row.employer_confirmed_at or row.candidate_objection_at:
        fail('Можно изменить или отменить только предстоящую неподтверждённую встречу')
    if cancel:
        row.status = 'cancelled'
        event(session, row.employer_id, f'meeting-cancelled:{row.id}', 'meeting_cancelled', -2, 'Назначенная встреча отменена')
    else:
        instant = data.scheduled_at
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=ZoneInfo(data.timezone))
        instant = utc(instant)
        if instant <= now(session):
            fail('Встреча должна быть в будущем',422)
        row.scheduled_at, row.timezone, row.channel = instant, data.timezone, data.channel
    session.flush()
    return row
