"""Targeted PostgreSQL/service checks for additive hiring workflows."""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import get_settings, Settings
from app.modules.auth.models import User, UserRole
from app.modules.employers.models import EmployerProfile, Offer, OfferStatus, SalaryCurrency
from app.modules.career.models import Opportunity, Application, Meeting, ActivityEvent, DemoClock, PrivacyConsent
from app.modules.career.schemas import OpportunityInput
from app.modules.career import service as s
from app.modules.assessments import service as assessment
from app.modules.assessments.models import CandidateCategory, CategoryStatus
from app.modules.matching.publication import csrf_token
from app.modules.auth.security import create_access_token

@pytest.fixture
def career(database):
    if database[0].dialect.name != 'postgresql':
        pytest.skip('Set MATCHING_TEST_DATABASE_URL for actual PostgreSQL constraint checks')
    with Session(database[0],expire_on_commit=False) as db:
        e=db.get(User,database[1]['employer'].id);c=db.get(User,database[1]['candidate'].id)
        e.is_email_verified=c.is_email_verified=True
        company=EmployerProfile(user_id=e.id,company_name='Тестовая компания',description='Подбор ИТ',industry='ИТ',contact_email='hr@example.com')
        db.add(company);db.flush();s.consent(db,c.id,'processing',True);db.commit()
        yield db,e,c,company

def payload(**values):
    return OpportunityInput(title='Backend разработчик',description='Разработка API и работа с PostgreSQL',specialization='backend',grade='middle',skills='Python, SQL',salary_from=100000,salary_to=200000,work_format='remote',contact_method='Внутренние сообщения',**values)

def job(db,e):return s.save_opportunity(db,e.id,'vacancy',payload())

def test_owner_application_and_contact_scope(career):
    db,e,c,company=career;row=job(db,e)
    assert not s.permitted_pair(db,company.id,s.candidate(db,c.id).id)
    application=s.apply(db,c.id,row.id,'Интересно')
    assert s.apply(db,c.id,row.id,'Повтор').id==application.id
    s.decide(db,e.id,application.id,'accepted');s.decide(db,e.id,application.id,'accepted')
    assert db.scalar(select(func.count(ActivityEvent.id)))==1
    outsider=User(email='other-company@example.com',password_hash='unused',role=UserRole.EMPLOYER,is_email_verified=True)
    db.add(outsider);db.flush();other=EmployerProfile(user_id=outsider.id,company_name='Другая');db.add(other);db.flush()
    with pytest.raises(HTTPException):s.owner(db,outsider.id,row.id)
    with pytest.raises(HTTPException):s.decide(db,outsider.id,application.id,'accepted')
    with pytest.raises(HTTPException):s.pair_access(db,outsider,company.id,s.candidate(db,c.id).id)
    assert not s.permitted_pair(db,other.id,s.candidate(db,c.id).id)

def test_lifecycle_boundaries_repost_and_idempotency(career,monkeypatch):
    db,e,c,company=career;row=job(db,e);start=row.created_at
    monkeypatch.setattr(s,'now',lambda db:start+timedelta(days=14))
    assert s.process_due(db)[0]['new']=='stable';assert s.process_due(db)==[]
    edited=payload().model_copy(update={'title':'Другая роль'})
    with pytest.raises(HTTPException):s.save_opportunity(db,e.id,'vacancy',edited,row.id)
    editable=payload().model_copy(update={'salary_to':210000,'description':'Новые условия работы без смены требований'})
    s.save_opportunity(db,e.id,'vacancy',editable,row.id)
    with pytest.raises(HTTPException):s.change_opportunity(db,e.id,row.id,'extend')
    s.apply(db,c.id,row.id,'Отклик');aid=db.scalar(select(Application.id));s.decide(db,e.id,aid,'rejected')
    s.change_opportunity(db,e.id,row.id,'extend');assert row.created_at==start
    monkeypatch.setattr(s,'now',lambda db:s.utc(row.expires_at))
    assert s.process_due(db)[0]['new']=='inactive'
    s.change_opportunity(db,e.id,row.id,'restore');assert row.created_at==start
    s.change_opportunity(db,e.id,row.id,'delete')
    with pytest.raises(HTTPException):job(db,e)
    # A different role is not blocked globally.
    s.save_opportunity(db,e.id,'vacancy',edited)

def test_meeting_auto_confirmation_never_confirms_hire(career,monkeypatch):
    db,e,c,company=career;row=job(db,e);s.apply(db,c.id,row.id,'Интересно');cid=s.candidate(db,c.id).id
    instant=s.now(db)
    meeting=Meeting(employer_id=company.id,candidate_id=cid,scheduled_at=instant-timedelta(days=3),timezone='Europe/Moscow',channel='Встреча',status='scheduled')
    db.add(meeting);db.flush();s.meeting_action(db,e,meeting.id,'interview')
    deadline=s.utc(meeting.employer_confirmed_at)+timedelta(days=2)
    monkeypatch.setattr(s,'now',lambda db:deadline)
    assert s.process_due(db)[0]['new']=='confirmed';assert s.process_due(db)==[]
    assert meeting.employer_hire_at is None and meeting.candidate_hire_at is None
    s.meeting_action(db,e,meeting.id,'hire');assert meeting.status=='confirmed'
    s.meeting_action(db,c,meeting.id,'hire');assert meeting.status=='hired'
    s.meeting_action(db,c,meeting.id,'hire')
    assert db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.kind=='hire'))==1

def test_objection_blocks_auto(career,monkeypatch):
    db,e,c,company=career;row=job(db,e);s.apply(db,c.id,row.id,'Отклик');instant=s.now(db)
    meeting=Meeting(employer_id=company.id,candidate_id=s.candidate(db,c.id).id,scheduled_at=instant-timedelta(days=1),employer_confirmed_at=instant,timezone='UTC',channel='Встреча',status='scheduled')
    db.add(meeting);db.flush();s.meeting_action(db,c,meeting.id,'object')
    monkeypatch.setattr(s,'now',lambda db:instant+timedelta(days=7))
    s.process_due(db);assert meeting.status=='disputed';assert not meeting.interview_confirmed_at

def test_schedule_timezone_future_duplicate_and_participant_access(career):
    from app.modules.career.schemas import MeetingInput
    db,e,c,company=career;row=job(db,e);cid=s.candidate(db,c.id).id
    future=s.now(db)+timedelta(days=1)
    payload=MeetingInput(scheduled_at=future,timezone='Europe/Moscow',channel='Видеовстреча')
    with pytest.raises(HTTPException):s.schedule(db,e.id,cid,payload)
    s.apply(db,c.id,row.id,'Отклик')
    with pytest.raises(HTTPException):s.schedule(db,e.id,cid,payload.model_copy(update={'scheduled_at':s.now(db)-timedelta(days=1)}))
    meeting=s.schedule(db,e.id,cid,payload)
    assert s.utc(meeting.scheduled_at)==future
    assert s.meetings_for(db,e)[0].id==s.meetings_for(db,c)[0].id==meeting.id
    with pytest.raises(HTTPException):s.schedule(db,e.id,cid,payload)

def test_ranking_visibility_determinism_and_pagination(career):
    db,e,c,company=career;row=job(db,e)
    ranked,total=s.recommendations(db,row);assert total>=1
    ids=[r['card'].profile_id for r in ranked];assert database_hidden_id(db) not in ids
    assert ids==[r['card'].profile_id for r in s.recommendations(db,row)[0]]
    first,_=s.recommendations(db,row,1,1);second,_=s.recommendations(db,row,2,1)
    assert first and (not second or first[0]['card'].profile_id!=second[0]['card'].profile_id)
    assert any('Заявленные' in reason for reason in first[0]['reasons'])

def database_hidden_id(db):
    from app.modules.candidates.models import CandidateProfile
    return db.scalar(select(CandidateProfile.id).where(CandidateProfile.is_searchable.is_(False)))

def test_processing_and_publication_persist(career):
    from app.modules.matching.service import set_publication
    db,e,c,company=career;s.consent(db,c.id,'processing',False)
    with pytest.raises(HTTPException):set_publication(db,c.id,True)
    s.consent(db,c.id,'processing',True);assert set_publication(db,c.id,True)
    assert db.scalar(select(PrivacyConsent).where(PrivacyConsent.user_id==c.id,PrivacyConsent.kind=='publication')).accepted
    assert set_publication(db,c.id,False) is False

def test_revoked_processing_denies_existing_contacts_html_api_and_pdf(career,client):
    db,e,c,company=career;cid=s.candidate(db,c.id).id
    from app.modules.employers import service as offers
    offer=Offer(employer_profile_id=company.id,candidate_profile_id=cid,title='Прямое предложение',salary_from=1,salary_to=2,salary_currency=SalaryCurrency.RUB,status=OfferStatus.ACCEPTED)
    db.add(offer);db.flush();oid=offer.id;db.commit()
    assert offers.get_offer_for_employer(db,employer_user_id=e.id,offer_id=oid).contacts.email==c.email
    s.consent(db,c.id,'processing',False);db.commit()
    headers={'Authorization':'Bearer '+create_access_token(e.id)}
    assert client.get(f'/career/threads/{company.id}/{cid}',headers=headers).status_code==404
    assert client.get(f'/career/resume/{cid}.pdf',headers=headers).status_code==404
    response=client.get(f'/api/v1/employers/offers/{oid}',headers=headers)
    assert response.status_code==200 and response.json()['contacts'] is None
    assert c.email not in client.get(f'/employer/offers/{oid}',headers=headers).text

def test_failed_verification_preserves_current(career):
    db,e,c,company=career;p=s.candidate(db,c.id)
    from app.modules.assessments.models import Category
    category=db.scalar(select(Category).where(Category.id==db.scalar(select(CandidateCategory.category_id).where(CandidateCategory.candidate_profile_id==p.id))))
    record=assessment._apply_category(db,candidate_profile_id=p.id,specialization_id=category.specialization_id,grade_id=category.grade_id,passed=False,confirmed_at=None,test_score=10)
    assert not record.is_current
    assert db.scalar(select(CandidateCategory.id).where(CandidateCategory.candidate_profile_id==p.id,CandidateCategory.is_current.is_(True),CandidateCategory.status==CategoryStatus.CONFIRMED))

def test_leaderboard_no_repeat_profile_or_interaction(career):
    db,e,c,company=career;row=job(db,e);s.apply(db,c.id,row.id,'Отклик');cid=s.candidate(db,c.id).id
    s.send_message(db,e,company.id,cid,'Здравствуйте');s.send_message(db,c,company.id,cid,'Добрый день')
    s.send_message(db,c,company.id,cid,'Уточнение')
    first=s.leaderboard(db);second=s.leaderboard(db)
    assert first[0]['score']==second[0]['score']==8
    assert db.scalar(select(func.count(ActivityEvent.id)))==2

def test_career_pages_and_forbidden_company(career,client):
    db,e,c,company=career;row=job(db,e);s.apply(db,c.id,row.id,'Отклик');db.commit()
    headers={'Authorization':'Bearer '+create_access_token(e.id)}
    for path in ['/career/opportunities','/career/opportunities?kind=need','/career/opportunities/new','/career/opportunities/'+str(row.id),'/career/applications','/career/connections','/career/meetings','/career/leaderboard']:
        assert client.get(path,headers=headers).status_code==200,path
    assert client.get('/career/opportunities/new',headers={'Authorization':'Bearer '+create_access_token(c.id)}).status_code==403
    assert client.post('/design-preview/time',headers=headers,data={'days':'1','token':csrf_token(e.id)}).status_code==404

def test_demo_separate_db_guard():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):Settings(demo_mode=True,database_url='postgresql+psycopg://localhost/project')
    with pytest.raises(ValidationError):Settings(demo_mode=True,database_url='postgresql+psycopg://localhost/fspcareer_demo')
    assert Settings(demo_mode=True,database_url='postgresql+psycopg://localhost/fspcareer_demo',jwt_secret_key='separate-demo-fixture-only-signing-key').demo_mode

def test_real_scoring_and_safe_repeats(career):
    from app.modules.assessments.models import Question,QuestionType,TestAttempt,TestAnswer,AttemptStatus,Category
    db,e,c,company=career
    category=db.scalar(select(Category).limit(1))
    question=Question(specialization_id=category.specialization_id,grade_id=category.grade_id,type=QuestionType.SINGLE_CHOICE,payload={'text':'Проверка','options':['a','b']},correct_answer={'value':'a'},difficulty=1)
    db.add(question);db.flush()
    for correct,total,expected in [(0,10,0),(1,10,10),(5,10,50),(9,10,90),(10,10,100),(3,4,75)]:
        attempt=TestAttempt(candidate_profile_id=s.candidate(db,c.id).id,specialization_id=category.specialization_id,declared_grade_id=category.grade_id,target_grade_id=category.grade_id,status=AttemptStatus.IN_PROGRESS)
        db.add(attempt);db.flush()
        for i in range(total):
            answer=TestAnswer(test_attempt_id=attempt.id,question_id=question.id,question_snapshot={'text':'Проверка','type':'single_choice','options':['a','b'],'correct':'a'})
            db.add(answer);db.flush()
            value={'value':'a' if i<correct else 'b'}
            assessment.submit_answer(db,user_id=c.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload=value)
            assert assessment.submit_answer(db,user_id=c.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload=value).id==answer.id
            with pytest.raises(assessment.InvalidAnswer):
                assessment.submit_answer(db,user_id=c.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload={'value':'b' if i<correct else 'a'})
        result=assessment.finish_attempt(db,user_id=c.id,attempt_id=attempt.id)
        assert result.score==expected
        count=db.scalar(select(func.count(CandidateCategory.id)))
        with pytest.raises(assessment.AttemptAlreadyCompleted):
            assessment.finish_attempt(db,user_id=c.id,attempt_id=attempt.id)
        assert db.get(TestAttempt,attempt.id).score==expected
        assert db.scalar(select(func.count(CandidateCategory.id)))==count

def test_demo_operator_clock_and_scoped_reset(career,client,monkeypatch):
    from app.modules.career import demo
    from app.modules.career.models import DemoSet
    db,e,c,company=career;settings=get_settings()
    monkeypatch.setattr(settings,'demo_mode',True);monkeypatch.setattr(settings,'demo_operator_ids',str(e.id))
    calls=[];monkeypatch.setattr(demo,'mock_call',lambda method,path,payload=None:calls.append((method,path)) or [])
    headers={'Authorization':'Bearer '+create_access_token(e.id)}
    other={'Authorization':'Bearer '+create_access_token(c.id)}
    assert client.post('/design-preview/time',headers=other,data={'days':'2','token':csrf_token(c.id)}).status_code==403
    preserved=job(db,e);db.commit()
    assert client.post('/design-preview/sets',headers=headers,data={'password':'demo12345','token':csrf_token(e.id)}).status_code==200
    db.expire_all();sid=db.scalar(select(DemoSet.id))
    prepared=list(db.scalars(select(Opportunity).where(Opportunity.demo_set==sid)))
    assert sorted(o.status for o in prepared)==['inactive','inactive','new','stable']
    assert client.post('/design-preview/time',headers=headers,data={'days':'2','token':csrf_token(e.id)}).status_code==200
    db.expire_all();assert db.get(DemoClock,1).offset_days==2
    # Security tokens retain real-time validity while business time moves.
    assert client.get('/candidate/profile',headers=other).status_code==200
    assert client.post(f'/design-preview/sets/{sid}/reset',headers=headers,data={'token':csrf_token(e.id)},follow_redirects=False).status_code==303
    db.expire_all();assert db.get(Opportunity,preserved.id) is not None
    assert not db.get(DemoSet,sid)
    assert ('DELETE','/operator/sets/'+sid) in calls
