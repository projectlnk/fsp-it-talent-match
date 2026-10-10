"""Operator tools on an explicitly enabled, separate demonstration database."""
from datetime import timedelta
from uuid import uuid4
import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from pydantic import ValidationError
from app.core.config import get_settings
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user_optional
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import hash_password
from app.modules.candidates.models import CandidateProfile, CandidateSkill
from app.modules.employers.models import EmployerProfile
from app.modules.assessments.models import Specialization, Grade, Category, CandidateCategory, CategoryStatus
from app.modules.career.models import DemoClock, DemoSet, Opportunity, Application, ActivityEvent, Meeting, ThreadMessage, PrivacyConsent
from app.modules.career.schemas import OpportunityInput
from app.modules.career import service as s
from app.modules.career.web import form, render, redirect
from mock_fsp.schemas import Participant, Achievement

router = APIRouter(prefix='/design-preview', include_in_schema=False)

def operator(user=Depends(get_current_user_optional)):
    settings = get_settings()
    allowed = {v.strip() for v in settings.demo_operator_ids.split(',') if v.strip()}
    if not settings.demo_mode:
        raise HTTPException(404, 'Служебное управление отключено')
    if not user or not user.is_email_verified or str(user.id) not in allowed:
        raise HTTPException(403, 'Требуется подтверждённый аккаунт оператора отдельного demo-стенда')
    return user

def mock_call(method, path, payload=None):
    settings = get_settings()
    try:
        with httpx.Client(base_url=settings.fsp_base_url, timeout=5) as client:
            response = client.request(method, path, json=payload,
                headers={'X-Demo-Key':settings.demo_mock_key.get_secret_value()})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        raise HTTPException(503, 'Тестовый реестр недоступен или управление не настроено')

def overview(request, user, db, **context):
    allowed={v.strip() for v in get_settings().demo_operator_ids.split(',') if v.strip()}
    is_operator = get_settings().demo_mode and user and user.is_email_verified and str(user.id) in allowed
    participants, registry_error = [], None
    if is_operator:
        try:
            participants = mock_call('GET','/participants')
            for participant in participants:
                participant['achievements'] = mock_call('GET',f"/participants/{participant['id']}/achievements")
        except HTTPException as exc:
            registry_error = exc.detail
    return render(request,user,'demo', enabled=get_settings().demo_mode,is_operator=is_operator,
        business_now=s.now(db), offset=(db.get(DemoClock,1).offset_days if is_operator and db.get(DemoClock,1) else 0),
        sets=list(db.scalars(select(DemoSet))) if is_operator else [], participants=participants,registry_error=registry_error,
        rating=s.leaderboard(db) if is_operator else [], **context)

@router.get('')
def index(request: Request, user=Depends(get_current_user_optional), db: Session=Depends(get_session)):
    response=overview(request,user,db)
    if get_settings().demo_mode:
        db.commit()
    return response

@router.post('/time')
async def advance(request: Request,user=Depends(operator),db: Session=Depends(get_session)):
    data=await form(request,user)
    if data.get('days') not in ('0','1','2','7','14','30'):
        raise HTTPException(422,'Выберите предусмотренный шаг')
    # Lock operator/user first, then single DB clock row: shared across requests and workers.
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    from sqlalchemy.dialects.postgresql import insert
    db.execute(insert(DemoClock).values(id=1,offset_days=0).on_conflict_do_nothing(index_elements=['id']))
    clock=db.scalar(select(DemoClock).where(DemoClock.id==1).with_for_update())
    before=s.now(db)
    if data['days']=='0': clock.offset_days=0
    else: clock.offset_days+=int(data['days'])
    db.flush()
    changes=s.process_due(db)
    response=overview(request,user,db,before=before,changes=changes,notice='Общее время стенда изменено. Состояния не откатываются при сбросе часов.')
    db.commit()
    return response

@router.post('/registry/{kind}')
async def registry(request: Request,kind: str,user=Depends(operator),db: Session=Depends(get_session)):
    data=await form(request,user)
    try:
        if kind=='participants': payload=Participant.model_validate(data)
        elif kind=='achievements':
            for key in ('competition_date','place'):
                if data.get(key)=='':data[key]=None
            payload=Achievement.model_validate(data)
        else:raise HTTPException(404,'Раздел не найден')
    except ValidationError:
        raise HTTPException(422,'Проверьте идентификаторы, дату и место')
    mock_call('PUT','/operator/'+kind,payload.model_dump(mode='json'))
    return redirect('/design-preview#registry')

def seed_set(db, password):
    """Explicit fixtures, clearly marked; never called during normal startup."""
    sid='scenario-'+uuid4().hex[:12]
    e=User(email=f'{sid}-company@example.com',password_hash=hash_password(password),role=UserRole.EMPLOYER,is_email_verified=True)
    c=User(email=f'{sid}-candidate@example.com',password_hash=hash_password(password),role=UserRole.CANDIDATE,is_email_verified=True)
    db.add_all([e,c]);db.flush()
    company=EmployerProfile(user_id=e.id,company_name=f'Демо-компания {sid}',description='Подготовленный демонстрационный набор',industry='ИТ',contact_email=e.email)
    from app.modules.candidates.models import WorkFormat
    candidate=CandidateProfile(user_id=c.id,full_name=f'Демо-кандидат {sid}',phone='+7 000 000-00-00',is_searchable=True,work_format=WorkFormat.REMOTE)
    db.add_all([company,candidate]);db.flush()
    s.consent(db,c.id,'processing',True);s.consent(db,c.id,'publication',True)
    spec=db.scalar(select(Specialization).order_by(Specialization.id));grade=db.scalar(select(Grade).where(Grade.code=='junior'))
    category=db.scalar(select(Category).where(Category.specialization_id==spec.id,Category.grade_id==grade.id))
    if not category:
        category=Category(specialization_id=spec.id,grade_id=grade.id);db.add(category);db.flush()
    db.add(CandidateCategory(candidate_profile_id=candidate.id,category_id=category.id,status=CategoryStatus.CONFIRMED,is_current=True,test_score=90,confirmed_at=s.now(db)))
    db.add(CandidateSkill(candidate_profile_id=candidate.id,skill='Python'))
    instant=s.now(db)
    labels=['Перед окончанием редактирования','Перед истечением срока','Неактивная: достаточно активности','Неактивная: недостаточно активности']
    jobs=[]
    for i,label in enumerate(labels):
        row=s.save_opportunity(db,e.id,'vacancy',OpportunityInput(title=label,description='Тестовые задачи и условия демонстрационного набора',specialization=spec.code,grade='junior',skills='Python',salary_from=100000,salary_to=150000,work_format='remote',contact_method='Внутренние сообщения'))
        row.demo_set=sid;row.created_at=instant-timedelta(days=13 if i==0 else 29)
        row.expires_at=instant+timedelta(days=17 if i==0 else 1)
        if i==1:row.status='stable'
        if i>=2:row.status='inactive'
        jobs.append(row)
    application=s.apply(db,c.id,jobs[0].id,'Хочу обсудить предложение')
    active=Application(opportunity_id=jobs[2].id,candidate_id=candidate.id,message='Демонстрационный отклик',status='submitted',created_at=instant)
    db.add(active);db.flush();s.decide(db,e.id,active.id,'accepted')
    db.add(Meeting(employer_id=company.id,candidate_id=candidate.id,scheduled_at=instant-timedelta(days=1),employer_confirmed_at=instant-timedelta(days=1),timezone='Europe/Moscow',channel='Внутренний канал демонстрации',status='scheduled',demo_set=sid))
    db.add(DemoSet(id=sid,employer_user_id=e.id,candidate_user_id=c.id));db.flush()
    mock_call('PUT','/operator/participants',{'id':sid+'-participant','display_name':'Участник набора '+sid,'email':sid+'@example.com'})
    mock_call('PUT','/operator/achievements',{'id':sid+'-award','participant_id':sid+'-participant','title':'Достижение тестового набора','discipline_code':spec.code,'competition_name':'Тестовый турнир','competition_date':instant.date().isoformat(),'place':1})
    return sid,e.email,c.email

@router.post('/sets')
async def prepare(request: Request,user=Depends(operator),db: Session=Depends(get_session)):
    data=await form(request,user)
    password=data.get('password','')
    if not 8<=len(password)<=128:raise HTTPException(422,'Задайте пароль набора: 8–128 символов')
    sid,email1,email2=seed_set(db,password)
    response=overview(request,user,db,notice=f'Создан {sid}. Компания: {email1}; кандидат без ФСП: {email2}. Это подготовленные тестовые аккаунты, не проверка регистрации.')
    db.commit()
    return response

@router.post('/sets/{sid}/reset')
async def reset(request: Request,sid: str,user=Depends(operator),db: Session=Depends(get_session)):
    await form(request,user)
    row=db.get(DemoSet,sid)
    if not row:raise HTTPException(404,'Набор не найден')
    mock_call('DELETE','/operator/sets/'+sid)
    eid=s.employer(db,row.employer_user_id).id;cid=s.candidate(db,row.candidate_user_id).id
    # Remove only this set's account-owned data, including later real demo interactions.
    for model,condition in [(ThreadMessage,(ThreadMessage.employer_id==eid)|(ThreadMessage.candidate_id==cid)),(Meeting,(Meeting.employer_id==eid)|(Meeting.candidate_id==cid)),(ActivityEvent,ActivityEvent.employer_id==eid),
        (Application,(Application.opportunity_id.in_(select(Opportunity.id).where(Opportunity.employer_id==eid)))|(Application.candidate_id==cid)),(Opportunity,Opportunity.employer_id==eid),(PrivacyConsent,PrivacyConsent.user_id.in_([row.employer_user_id,row.candidate_user_id]))]:
        db.execute(delete(model).where(condition))
    ids=[row.employer_user_id,row.candidate_user_id];db.delete(row);db.flush()
    db.execute(delete(User).where(User.id.in_(ids)))
    db.commit()
    return redirect('/design-preview')
