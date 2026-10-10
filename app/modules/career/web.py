"""Working Jinja pages use the same transactional services as demo processing."""
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user
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
    user: User = Depends(verified), db: Session = Depends(get_session)):
    if kind not in ('need', 'vacancy'):
        raise HTTPException(422, 'Неизвестный раздел')
    s.process_due(db)
    query = select(Opportunity, EmployerProfile).join(EmployerProfile).where(Opportunity.kind == kind)
    if user.role == UserRole.EMPLOYER:
        query = query.where(EmployerProfile.user_id == user.id)
        query = query.where(Opportunity.status.in_(['inactive','deleted']) if archive else Opportunity.status.in_(['new','stable']))
    else:
        if kind != 'vacancy':
            raise HTTPException(403, 'Потребности доступны владельцу')
        query = query.where(Opportunity.status.in_(['new','stable']), Opportunity.expires_at > s.now(db))
    for key, value in [('specialization',specialization),('grade',grade),('work_format',work_format)]:
        if value:
            query = query.where(getattr(Opportunity,key) == value)
    rows = db.execute(query.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()).offset((page-1)*20).limit(21)).all()
    db.commit()
    return render(request,user,'opportunities', rows=rows[:20], has_more=len(rows)>20, page=page, kind=kind, archive=archive, **reference_filters(db))


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
    return render(request,user,'edit',item=item,kind=item.kind,**reference_filters(db))


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
def detail(request: Request, oid: int, page: int = Query(1, ge=1), user: User = Depends(verified), db: Session = Depends(get_session)):
    s.process_due(db)
    item = db.get(Opportunity,oid)
    if not item:
        raise HTTPException(404,'Запись не найдена')
    company = db.get(EmployerProfile,item.employer_id)
    if user.role == UserRole.EMPLOYER:
        s.owner(db,user.id,oid)
        recommendations,total = s.recommendations(db,item,page)
        applications = db.execute(select(Application,CandidateProfile).join(CandidateProfile).where(Application.opportunity_id==oid).order_by(Application.id)).all()
        # Applicants explicitly shared data with this company, including private profiles.
        applicant_scores = {c.id:s.applicant_rank(db,c,item) for _,c in applications}
        applications.sort(key=lambda pair:(not applicant_scores[pair[1].id]['category_match'],-applicant_scores[pair[1].id]['score'],pair[0].id))
    else:
        if item.kind != 'vacancy' or item.status not in ('new','stable'):
            raise HTTPException(404,'Вакансия недоступна')
        recommendations,total,applications,applicant_scores = [],0,[],{}
    db.commit()
    return render(request,user,'detail',item=item,company=company,recommendations=recommendations,total=total,
                  applications=applications,applicant_scores=applicant_scores,page=page)


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
def applications(request: Request, user: User = Depends(verified), db: Session = Depends(get_session)):
    query = select(Application,Opportunity,EmployerProfile,CandidateProfile).select_from(Application).join(Opportunity,Opportunity.id==Application.opportunity_id).join(EmployerProfile,EmployerProfile.id==Opportunity.employer_id).join(CandidateProfile,CandidateProfile.id==Application.candidate_id)
    query = query.where(EmployerProfile.user_id==user.id) if user.role==UserRole.EMPLOYER else query.where(CandidateProfile.user_id==user.id)
    return render(request,user,'applications',rows=db.execute(query.order_by(Application.id.desc())).all())


@router.post('/applications/{aid}/decision')
async def decision(request: Request, aid: int, user: User = Depends(verified), db: Session = Depends(get_session)):
    role(user,'employer')
    data = await form(request,user)
    s.decide(db,user.id,aid,data.get('decision'))
    db.commit()
    return redirect('/career/applications?saved=1')


@router.get('/leaderboard')
def leaderboard(request: Request, user: User = Depends(verified), db: Session = Depends(get_session)):
    rows = s.leaderboard(db)
    db.commit()
    return render(request,user,'leaderboard',rows=rows)


@router.get('/connections')
def connections(request: Request,user: User = Depends(verified),db: Session = Depends(get_session)):
    if user.role==UserRole.EMPLOYER:
        eid=s.employer(db,user.id).id
        ids=set(db.scalars(select(Offer.candidate_profile_id).where(Offer.employer_profile_id==eid,Offer.status==OfferStatus.ACCEPTED)))
        ids.update(db.scalars(select(Application.candidate_id).join(Opportunity).where(Opportunity.employer_id==eid)))
        rows=[(eid,c.id,c.full_name) for c in db.scalars(select(CandidateProfile).where(CandidateProfile.id.in_(ids)))]
    else:
        cid=s.candidate(db,user.id).id
        ids=set(db.scalars(select(Offer.employer_profile_id).where(Offer.candidate_profile_id==cid,Offer.status==OfferStatus.ACCEPTED)))
        ids.update(db.scalars(select(Opportunity.employer_id).join(Application).where(Application.candidate_id==cid)))
        rows=[(e.id,cid,e.company_name) for e in db.scalars(select(EmployerProfile).where(EmployerProfile.id.in_(ids)))]
    return render(request,user,'connections',rows=rows)


@router.get('/threads/{eid}/{cid}')
def thread(request: Request,eid: int,cid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    company,profile=s.pair_access(db,user,eid,cid)
    person=db.get(User,profile.user_id)
    messages=db.scalars(select(ThreadMessage).where(ThreadMessage.employer_id==eid,ThreadMessage.candidate_id==cid).order_by(ThreadMessage.id)).all()
    return render(request,user,'thread',company=company,profile=profile,person=person,messages=messages,eid=eid,cid=cid)


@router.post('/threads/{eid}/{cid}')
async def message(request: Request,eid: int,cid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    data=await form(request,user)
    s.send_message(db,user,eid,cid,data.get('body',''))
    db.commit()
    return redirect(f'/career/threads/{eid}/{cid}')


@router.get('/meetings')
def meetings(request: Request,user: User = Depends(verified),db: Session = Depends(get_session)):
    s.process_due(db)
    rows=s.meetings_for(db,user)
    db.commit()
    return render(request,user,'meetings',rows=rows,local_time=lambda m:s.utc(m.scheduled_at).astimezone(ZoneInfo(m.timezone)).strftime('%d.%m.%Y %H:%M'))


@router.post('/meetings')
async def schedule(request: Request,user: User = Depends(verified),db: Session = Depends(get_session)):
    role(user,'employer')
    data=await form(request,user)
    try:
        cid=int(data.pop('candidate_id'))
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
    return redirect('/candidate/profile#visibility')


@router.get('/resume/{cid}.pdf')
def recipient_pdf(cid: int,user: User = Depends(verified),db: Session = Depends(get_session)):
    role(user,'employer')
    company=s.employer(db,user.id)
    _,profile=s.pair_access(db,user,company.id,cid)
    from app.modules.candidates.resume import generate_resume_pdf
    return Response(generate_resume_pdf(db,user_id=profile.user_id),media_type='application/pdf',headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename=resume.pdf'})
