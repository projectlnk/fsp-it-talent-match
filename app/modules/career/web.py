"""Working Jinja pages use the same transactional services as demo processing."""
from zoneinfo import ZoneInfo
from datetime import date
import calendar
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, Response, JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user, get_current_user_optional
from app.modules.auth.models import User, UserRole
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import EmployerProfile, Offer, OfferStatus
from app.modules.matching.publication import csrf_token, check_csrf
from app.modules.matching.service import reference_filters
from app.modules.career import service as s
from app.modules.career.models import Opportunity, Application, Meeting, ThreadMessage, PrivacyConsent
from app.modules.career.schemas import OpportunityInput, MeetingInput
from app.web.templates import templates

router = APIRouter(prefix='/career', include_in_schema=False)


def verified(user: User = Depends(get_current_user)):
    if not user.is_email_verified:
        raise HTTPException(403, 'Подтвердите email: откройте письмо или /auth/check-email')
    return user


def role(user, value):
    if user.role.value != value:
        raise HTTPException(403, 'Недостаточно прав')


def render(request, user, name, **context):
    response = templates.TemplateResponse(request=request, name='career/' + name + '.html',
        context={'user':user, 'csrf_token':csrf_token(user.id) if user else '', **context})
    response.headers['Cache-Control'] = 'no-store'
    return response


def redirect(path):
    return RedirectResponse(path, status_code=303)


async def form(request, user):
    data = dict(await request.form())
    check_csrf(request, user.id, data.pop('token', ''))
    return data


@router.get('/opportunities')
def opportunities(request: Request, kind: str = 'vacancy', archive: bool = False,
    specialization: str = '', grade: str = '', work_format: str = '', page: int = Query(1, ge=1),
    user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_session), company_id: int | None = Query(None,ge=1)):
    if kind not in ('need', 'vacancy'):
        raise HTTPException(422, 'Неизвестный раздел')
    if user and user.role == UserRole.EMPLOYER:
        verified(user)
    s.process_due(db)
    query = select(Opportunity, EmployerProfile).join(EmployerProfile).where(Opportunity.kind == kind)
    if user and user.role == UserRole.EMPLOYER:
        query = query.where(EmployerProfile.user_id == user.id)
        query = query.where(Opportunity.status.in_(['inactive','deleted']) if archive else Opportunity.status.in_(['new','stable']))
    else:
        if kind != 'vacancy':
            raise HTTPException(403, 'Потребности доступны владельцу')
        query = query.where(Opportunity.status.in_(['new','stable']), Opportunity.expires_at > s.now(db))
    if company_id is not None:
        query = query.where(Opportunity.employer_id == company_id)
    query = query.join(User, User.id == EmployerProfile.user_id).where(User.is_active.is_(True), User.role == UserRole.EMPLOYER)
    for key, value in [('specialization',specialization),('grade',grade),('work_format',work_format)]:
        if value:
            query = query.where(getattr(Opportunity,key) == value)
    ordering = [Opportunity.created_at.desc(), Opportunity.id.desc()] if user and user.role == UserRole.EMPLOYER else [s.vacancy_activity_order().desc(), Opportunity.created_at.desc(), Opportunity.id.desc()]
    rows = db.execute(query.order_by(*ordering).offset((page-1)*20).limit(21)).all()
    counts = dict(db.execute(select(Application.opportunity_id,func.count(Application.id)).where(Application.opportunity_id.in_([r[0].id for r in rows])).group_by(Application.opportunity_id)).all())
    states = {r[0].id:s.opportunity_state(db,r[0]) for r in rows} if user and user.role == UserRole.EMPLOYER else {}
    db.commit()
    return render(request,user,'opportunities', rows=rows[:20], counts=counts, states=states, has_more=len(rows)>20, page=page, kind=kind, archive=archive, **reference_filters(db))


@router.get('/opportunities/new')
def new(request: Request, kind: str = 'vacancy', user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'employer')
    if kind not in ('need','vacancy'):
        raise HTTPException(422, 'Неверный тип')
    return render(request,user,'edit', item=None, kind=kind, **reference_filters(db))


@router.get('/opportunities/{oid}/edit')
def edit(request: Request, oid: int, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'employer')
    item = s.owner(db,user.id,oid)
    return render(request,user,'edit',item=item,kind=item.kind,state=s.opportunity_state(db,item),**reference_filters(db))


@router.post('/opportunities/save')
async def save(request: Request, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'employer')
    data = await form(request,user)
    oid, kind = data.pop('id',''), data.pop('kind','vacancy')
    if kind not in ('need','vacancy'):
        raise HTTPException(422,'Неверный тип')
    try:
        payload = OpportunityInput.model_validate(data)
        row = s.save_opportunity(db,user.id,kind,payload,int(oid) if oid else None)
    except (ValidationError, ValueError):
        return render(request,user,'edit',item={**data,'id':oid},kind=kind,error='Проверьте обязательные поля, грейд, формат и диапазон зарплаты',**reference_filters(db))
    db.commit()
    return redirect(f'/career/opportunities/{row.id}?saved=1')


@router.get('/opportunities/{oid}')
def detail(request: Request, oid: int, page: int = Query(1, ge=1), user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_session)):
    if user and user.role == UserRole.EMPLOYER:
        verified(user)
    s.process_due(db)
    item = db.get(Opportunity,oid)
    if not item:
        raise HTTPException(404,'Запись не найдена')
    company = db.get(EmployerProfile,item.employer_id)
    if user and user.role == UserRole.EMPLOYER:
        s.owner(db,user.id,oid)
        recommendations,total = s.recommendations(db,item,page)
        applications = db.execute(select(Application,CandidateProfile).join(CandidateProfile).where(Application.opportunity_id==oid).order_by(Application.id)).all()
        # Applicants explicitly shared data with this company, including private profiles.
        applicant_scores = {c.id:s.applicant_rank(db,c,item) for _,c in applications}
        applications.sort(key=lambda pair:(not applicant_scores[pair[1].id]['category_match'],-applicant_scores[pair[1].id]['score'],pair[0].id))
    else:
        company_user = db.get(User,company.user_id)
        own_history = bool(user and user.is_email_verified and user.role == UserRole.CANDIDATE and db.scalar(select(Application.id).join(CandidateProfile).where(Application.opportunity_id == oid, CandidateProfile.user_id == user.id)))
        own_history = own_history or bool(user and user.is_email_verified and user.role == UserRole.CANDIDATE and db.scalar(select(Offer.id).join(CandidateProfile,CandidateProfile.id==Offer.candidate_profile_id).where(Offer.opportunity_id==oid,Offer.status==OfferStatus.ACCEPTED,CandidateProfile.user_id==user.id)))
        if item.kind != 'vacancy' or (not own_history and (item.status not in ('new','stable') or s.utc(item.expires_at) <= s.now(db) or not company_user.is_active or company_user.role != UserRole.EMPLOYER)):
            raise HTTPException(404,'Вакансия недоступна')
        recommendations,total,applications,applicant_scores = [],0,[],{}
    back = request.query_params.get('return_to','')
    return_to = back if (back == '/career/opportunities' or back.startswith('/career/opportunities?')) and not any(ord(c)<32 or c == chr(92) for c in back) else '/career/opportunities'
    own_application = db.scalar(select(Application).where(Application.opportunity_id == oid, Application.candidate_id == s.candidate(db,user.id).id)) if user and user.is_email_verified and user.role == UserRole.CANDIDATE else None
    db.commit()
    return render(request,user,'detail',item=item,company=company,recommendations=recommendations,total=total,
                  applications=applications,applicant_scores=applicant_scores,page=page,return_to=return_to,own_application=own_application,state=s.opportunity_state(db,item) if user and user.role == UserRole.EMPLOYER else None)


@router.post('/opportunities/{oid}/action')
async def action(request: Request, oid: int, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'employer')
    data = await form(request,user)
    row = s.change_opportunity(db,user.id,oid,data.get('action'))
    db.commit()
    return redirect(f'/career/opportunities/{row.id}?saved=1')


@router.post('/opportunities/{oid}/apply')
async def apply(request: Request, oid: int, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'candidate')
    data = await form(request,user)
    if data.get('share_contacts') != 'yes':
        raise HTTPException(422,'Подтвердите передачу контактов этой компании')
    message = data.get('message','').strip()
    if len(message)>2000:
        raise HTTPException(422,'Сообщение слишком длинное')
    s.apply(db,user.id,oid,message)
    db.commit()
    return redirect('/career/applications?saved=1')


@router.get('/applications')
def applications(request: Request, oid: int | None = None, user: User = Depends(verified), db: Session = Depends(get_session)):
    query = select(Application,Opportunity,EmployerProfile,CandidateProfile).select_from(Application).join(Opportunity,Opportunity.id==Application.opportunity_id).join(EmployerProfile,EmployerProfile.id==Opportunity.employer_id).join(CandidateProfile,CandidateProfile.id==Application.candidate_id)
    query = query.where(EmployerProfile.user_id==user.id) if user.role==UserRole.EMPLOYER else query.where(CandidateProfile.user_id==user.id)
    if oid is not None:
        if user.role == UserRole.EMPLOYER:
            s.owner(db,user.id,oid)
        query = query.where(Application.opportunity_id == oid)
    rows = db.execute(query.order_by(Application.id.desc())).all()
    accessible = {(company.id,c.id):s.accepted_pair(db,company.id,c.id) for a,job,company,c in rows}
    return render(request,user,'applications',rows=rows,accessible=accessible)


@router.get('/applicants/{aid}')
def applicant(request: Request, aid: int, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user, 'employer')
    company = s.employer(db, user.id)
    application = db.scalar(select(Application).join(Opportunity).where(Application.id == aid,
        Opportunity.employer_id == company.id))
    if not application or not s.can_view_candidate(db, company.id, application.candidate_id):
        raise HTTPException(404, 'Отклик недоступен')
    profile = db.get(CandidateProfile, application.candidate_id)
    job = db.get(Opportunity, application.opportunity_id)
    application.resume_viewed_at = application.resume_viewed_at or s.now(db)
    db.commit()
    return render(request,user,'applicant',profile=profile,item=job,application=application,
        can_chat=s.accepted_pair(db,company.id,profile.id),company=company)


@router.post('/applications/{aid}/decision')
async def decision(request: Request, aid: int, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'employer')
    data = await form(request,user)
    s.decide(db,user.id,aid,data.get('decision'))
    db.commit()
    return redirect('/career/applications?saved=1')


@router.get('/leaderboard')
def leaderboard(request: Request, user: User = Depends(verified), db: Session = Depends(get_session)):
    s.process_due(db)
    rows = s.leaderboard(db)
    db.commit()
    return render(request,user,'leaderboard',rows=rows,current=next((r for r in rows if r['company'].user_id == user.id),None))


@router.get('/connections')
def connections(request: Request,user: User = Depends(verified),db: Session = Depends(get_session)):
    rows=s.connections_for(db,user)
    offers=[]
    if user.role == UserRole.EMPLOYER:
        from app.modules.employers.service import list_employer_offers
        offers=list_employer_offers(db,user.id)
    if user.role == UserRole.CANDIDATE:
        from app.modules.employers.service import list_candidate_offers
        offers=list_candidate_offers(db,user.id)
    latest={}
    for eid,cid,_ in rows:
        latest[cid if user.role == UserRole.EMPLOYER else eid]=db.scalar(select(ThreadMessage).where(ThreadMessage.employer_id==eid,ThreadMessage.candidate_id==cid).order_by(ThreadMessage.id.desc()).limit(1))
    return render(request,user,'connections',rows=rows,offers=offers,latest=latest,
                  employer_id=s.employer(db,user.id).id if user.role == UserRole.EMPLOYER else None)


@router.get('/threads/{eid}/{cid}')
def thread(request: Request,eid: int,cid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    company,profile=s.pair_access(db,user,eid,cid)
    person=db.get(User,profile.user_id)
    messages=db.scalars(select(ThreadMessage).where(ThreadMessage.employer_id==eid,ThreadMessage.candidate_id==cid).order_by(ThreadMessage.created_at,ThreadMessage.id)).all()
    if user.role == UserRole.EMPLOYER and s.can_view_candidate(db,eid,cid):
        s.record_resume_view(db,user,cid)
        db.commit()
    return render(request,user,'thread',company=company,profile=profile,person=person,messages=messages,eid=eid,cid=cid,can_view=s.can_view_candidate(db,eid,cid),can_send=s.accepted_pair(db,eid,cid),last_message=max((m.id for m in messages),default=0))


@router.get('/threads/{eid}/{cid}/messages')
def message_feed(eid: int,cid: int,after: int = Query(0,ge=0),user: User = Depends(verified),db: Session = Depends(get_session)):
    s.pair_access(db,user,eid,cid)
    messages=db.scalars(select(ThreadMessage).where(ThreadMessage.employer_id==eid,ThreadMessage.candidate_id==cid,ThreadMessage.id>after).order_by(ThreadMessage.id).limit(100)).all()
    return JSONResponse({'can_send':s.accepted_pair(db,eid,cid), 'can_view':s.can_view_candidate(db,eid,cid), 'messages':[{'id':m.id,'own':m.author_id==user.id,'body':m.body,'created_at':m.created_at.isoformat(),'technical':m.kind != 'message'} for m in messages]},headers={'Cache-Control':'no-store'})


@router.post('/threads/{eid}/{cid}')
async def message(request: Request,eid: int,cid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    data=await form(request,user)
    s.send_message(db,user,eid,cid,data.get('body',''))
    db.commit()
    return redirect(f'/career/threads/{eid}/{cid}')


@router.get('/meetings')
def meetings(request: Request, month: str = '', timezone: str = 'Europe/Moscow', user: User = Depends(verified),db: Session = Depends(get_session)):
    s.process_due(db)
    rows=s.meetings_for(db,user)
    pairs=s.connections_for(db,user)
    creatable_pairs=[p for p in pairs if s.accepted_pair(db,p[0],p[1])]
    names={cid:name for _,cid,name in pairs} if user.role == UserRole.EMPLOYER else {eid:name for eid,_,name in pairs}
    if user.role == UserRole.EMPLOYER:
        rows=[m for m in rows if m.candidate_id in names]
    else:
        rows=[m for m in rows if m.employer_id in names]
    try:
        zone=ZoneInfo(timezone)
        first=date.fromisoformat(month+'-01') if month else s.now(db).astimezone(zone).date().replace(day=1)
        if not 1901 <= first.year <= 2099:
            raise ValueError()
    except (ValueError,KeyError):
        raise HTTPException(422,'Проверьте месяц и часовой пояс календаря')
    by_day={}
    for m in rows:
        local=s.utc(m.scheduled_at).astimezone(zone)
        if local.year == first.year and local.month == first.month:
            by_day.setdefault(local.day,[]).append(m)
    previous=first.replace(year=first.year-1,month=12) if first.month==1 else first.replace(month=first.month-1)
    following=first.replace(year=first.year+1,month=1) if first.month==12 else first.replace(month=first.month+1)
    instant=s.now(db)
    db.commit()
    vacancy_contexts = db.execute(select(Offer,Opportunity,CandidateProfile).join(Opportunity,Opportunity.id==Offer.opportunity_id).join(CandidateProfile,CandidateProfile.id==Offer.candidate_profile_id).where(Offer.status==OfferStatus.ACCEPTED,Offer.employer_profile_id==s.employer(db,user.id).id)).all() if user.role == UserRole.EMPLOYER else []
    return render(request,user,'meetings',vacancy_contexts=vacancy_contexts,rows=rows,pairs=creatable_pairs,names=names,instant=instant,month=first.strftime('%Y-%m'),
                  weeks=calendar.monthcalendar(first.year,first.month),by_day=by_day,timezone=timezone,
                  previous=previous.strftime('%Y-%m'),following=following.strftime('%Y-%m'),today=instant.astimezone(zone).strftime('%Y-%m-%d'),
                  upcoming=sorted([m for m in rows if m.status=='scheduled' and s.utc(m.scheduled_at)>instant],key=lambda m:s.utc(m.scheduled_at)),
                  utc=s.utc,calendar_time=lambda m:s.utc(m.scheduled_at).astimezone(zone).strftime('%H:%M'),
                  local_input=lambda m:s.utc(m.scheduled_at).astimezone(ZoneInfo(m.timezone)).strftime('%Y-%m-%dT%H:%M'),
                  local_time=lambda m:s.utc(m.scheduled_at).astimezone(ZoneInfo(m.timezone)).strftime('%d.%m.%Y %H:%M'))


@router.post('/meetings/{mid}/update')
async def update_meeting(request: Request, mid: int, user: User = Depends(verified),db: Session = Depends(get_session)):
    role(user,'employer')
    data=await form(request,user)
    try:
        cancel=data.pop('action','')=='cancel'
        s.update_meeting(db,user,mid,None if cancel else MeetingInput.model_validate(data),cancel=cancel)
    except (ValueError,ValidationError):
        raise HTTPException(422,'Проверьте дату, часовой пояс и способ связи')
    db.commit()
    return redirect('/career/meetings?saved=1')


@router.post('/meetings')
async def schedule(request: Request,user: User = Depends(verified),db: Session = Depends(get_session)):
    role(user,'employer')
    data=await form(request,user)
    try:
        cid=int(data.pop('candidate_id'))
        if data.get('opportunity_id') == '':
            data['opportunity_id'] = None
        s.schedule(db,user.id,cid,MeetingInput.model_validate(data))
    except (ValueError,ValidationError):
        raise HTTPException(422,'Проверьте дату, часовой пояс и способ связи')
    db.commit()
    return redirect('/career/meetings?saved=1')


@router.post('/meetings/{mid}')
async def meeting_action(request: Request,mid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    data=await form(request,user)
    s.meeting_action(db,user,mid,data.get('action'))
    db.commit()
    return redirect('/career/meetings?saved=1')


@router.post('/consent')
async def consent(request: Request,user: User = Depends(get_current_user),db: Session = Depends(get_session)):
    role(user,'candidate')
    data=await form(request,user)
    accepted=data.get('processing')=='yes'
    s.consent(db,user.id,'processing',accepted)
    if not accepted:
        profile=s.candidate(db,user.id)
        profile.is_searchable=False
        s.consent(db,user.id,'publication',False)
    db.commit()
    return redirect('/candidate/profile?tab=settings#visibility')


@router.get('/resume/{cid}.pdf')
def recipient_pdf(cid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    role(user,'employer')
    company=s.employer(db,user.id)
    if not s.can_view_candidate(db,company.id,cid):
        raise HTTPException(404,'Данные кандидата недоступны')
    profile=s.candidate(db,db.get(CandidateProfile,cid).user_id)
    from app.modules.candidates.resume import generate_resume_pdf
    return Response(generate_resume_pdf(db,user_id=profile.user_id),media_type='application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename=resume.pdf'})


@router.get('/companies/{eid}')
def company_page(request: Request, eid: int, user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_session)):
    company = db.scalar(select(EmployerProfile).join(User).where(EmployerProfile.id==eid,User.is_active.is_(True),User.role==UserRole.EMPLOYER))
    if not company:
        raise HTTPException(404,'Компания не найдена')
    vacancies = db.execute(select(Opportunity).where(Opportunity.employer_id==eid,Opportunity.kind=='vacancy',Opportunity.status.in_(['new','stable']),Opportunity.expires_at>s.now(db)).order_by(Opportunity.created_at.desc()).limit(5)).scalars().all()
    return render(request,user,'company',company=company,vacancies=vacancies)
