"""Focused integration checks for the employer workspace, using owned fixture DBs."""
from datetime import timedelta
import re
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.modules.auth.models import User,UserRole
from app.modules.auth.security import create_access_token
from app.modules.employers.models import EmployerProfile,Offer,OfferStatus
from app.modules.career.models import ActivityEvent,Meeting,ThreadMessage,Application
from app.modules.matching.publication import csrf_token
from app.modules.career.schemas import MeetingInput
from app.modules.career import service as s
from app.modules.matching import service as matching
from app.modules.matching.schemas import CandidateSearchQuery
from app.modules.assessments.models import Question,QuestionType,TestAttempt,TestAnswer,AttemptStatus
from test_career_workflows import career,job,accept_invitation


def auth(user):return {'Authorization':'Bearer '+create_access_token(user.id)}


def test_sections_owned_cards_and_legacy_access(career,client):
    db,e,c,company=career
    active=job(db,e)
    from test_career_workflows import payload
    archived=s.save_opportunity(db,e.id,'vacancy',payload().model_copy(update={'title':'Архивная роль'}))
    s.change_opportunity(db,e.id,archived.id,'close')
    application=s.apply(db,c.id,active.id,'Отклик')
    foreign=User(email='outsider@example.com',password_hash='unused',role=UserRole.EMPLOYER,is_email_verified=True)
    db.add(foreign);db.flush();db.add(EmployerProfile(user_id=foreign.id,company_name='Чужая компания'));db.commit()
    response=client.get('/career/opportunities',headers=auth(e))
    sidebar=response.text.split('<aside class="sidebar">')[1].split('</aside>')[0]
    labels=[re.sub(r'<[^>]+>', '', body).strip() for body in re.findall(r'<a[^>]*>(.*?)</a>', sidebar, re.S)]
    assert labels==['Профиль компании','Мои вакансии','Потребность команды','Поиск кандидатов','Лидерборд','Связь']
    assert 'Архивная роль' not in response.text
    assert 'Архивная роль' in client.get('/career/opportunities?archive=true',headers=auth(e)).text
    for url in [f'/career/opportunities/{active.id}',f'/career/opportunities/{active.id}/edit','/career/applications','/employer/offers','/career/connections','/career/meetings','/career/leaderboard','/career/opportunities?kind=need']:
        assert client.get(url,headers=auth(e)).status_code==200,url
    assert client.get(f'/career/opportunities/{active.id}',headers=auth(foreign)).status_code==404
    assert client.get(f'/career/applications?oid={active.id}',headers=auth(foreign)).status_code==404
    assert client.post(f'/career/applications/{application.id}/decision',headers=auth(foreign),data={'token':csrf_token(foreign.id),'decision':'accepted'}).status_code==404


def test_meeting_changes_cancel_and_authorization(career,client):
    db,e,c,company=career;vacancy=job(db,e);s.apply(db,c.id,vacancy.id,'Отклик');cid=s.candidate(db,c.id).id
    accept_invitation(db,e,c,company)
    future=s.now(db)+timedelta(days=2)
    meeting=s.schedule(db,e.id,cid,MeetingInput(scheduled_at=future,timezone='UTC',channel='Онлайн'));db.commit()
    assert client.post(f'/career/meetings/{meeting.id}/update',headers=auth(c),data={'token':csrf_token(c.id),'action':'cancel'}).status_code==403
    assert client.post(f'/career/meetings/{meeting.id}/update',headers=auth(e),data={'token':csrf_token(e.id),'scheduled_at':(future+timedelta(days=1)).isoformat(),'timezone':'Europe/Moscow','channel':'Видеосвязь'},follow_redirects=False).status_code==303
    db.expire_all();assert db.get(Meeting,meeting.id).timezone=='Europe/Moscow'
    assert client.post(f'/career/meetings/{meeting.id}/update',headers=auth(e),data={'token':csrf_token(e.id),'action':'cancel'},follow_redirects=False).status_code==303
    db.expire_all();assert db.get(Meeting,meeting.id).status=='cancelled'
    with pytest.raises(HTTPException):s.update_meeting(db,e,meeting.id,cancel=True)
    replacement=s.schedule(db,e.id,cid,MeetingInput(scheduled_at=future,timezone='UTC',channel='Онлайн'))
    assert replacement.id!=meeting.id
    assert not db.scalar(select(ActivityEvent.id).where(ActivityEvent.kind=='interview'))
    db.commit()
    assert client.get('/career/meetings?month=oops',headers=auth(e)).status_code==422


def test_leaderboard_read_is_pure_and_views_do_not_reward(career):
    db,e,c,company=career;vacancy=job(db,e);s.apply(db,c.id,vacancy.id,'Отклик');cid=s.candidate(db,c.id).id
    before=db.scalar(select(func.count(ActivityEvent.id)))
    first=s.leaderboard(db);s.leaderboard(db)
    assert db.scalar(select(func.count(ActivityEvent.id)))==before
    s.record_resume_view(db,e,cid);s.record_resume_view(db,e,cid)
    after=s.leaderboard(db)[0]
    assert after['score']==first[0]['score']==0
    assert after['viewed']==0 and after['viewed_percent']==0
    # A general profile view must not count for every vacancy.
    assert db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.kind=='resume_view'))==1
    s.decide(db,e.id,db.scalar(select(Application.id)),'accepted')
    assert s.leaderboard(db)[0]['selected']==1


def test_pending_offer_is_not_chat_and_revoked_pair_is_hidden(career,client):
    db,e,c,company=career;cid=s.candidate(db,c.id).id
    db.add(Offer(employer_profile_id=company.id,candidate_profile_id=cid,title='Ожидающее приглашение',salary_from=1,salary_to=2,status=OfferStatus.SENT));db.commit()
    assert s.connections_for(db,e)==[]
    html=client.get('/career/connections',headers=auth(e)).text
    assert 'Ожидающее приглашение' in html and 'Ожидает ответа' in html
    assert client.get(f'/career/threads/{company.id}/{cid}',headers=auth(e)).status_code==404
    vacancy=job(db,e);s.apply(db,c.id,vacancy.id,'Отклик');db.commit()
    assert not s.connections_for(db,e)
    accept_invitation(db,e,c,company)
    assert s.connections_for(db,e)
    s.consent(db,c.id,'processing',False);db.commit()
    assert s.connections_for(db,e)==[]
    assert client.post(f'/career/threads/{company.id}/{cid}',headers=auth(e),data={'token':csrf_token(e.id),'body':'Запрещённое сообщение'}).status_code==404
    assert not db.scalar(select(ThreadMessage.id).where(ThreadMessage.kind=='message'))


def test_extended_filters_and_fsp_activity_ties(career,client):
    db,e,c,company=career
    from app.modules.candidates.models import CandidateProfile
    from app.modules.assessments.models import CandidateCategory
    profiles=list(db.scalars(select(CandidateProfile).order_by(CandidateProfile.id)))
    for p in profiles:p.experience_years=4;p.desired_salary_from=100000;p.desired_salary_to=200000
    for record in db.scalars(select(CandidateCategory)):record.test_score=80
    # Equal skills/test result: the existing demo achievement resolves the tie.
    result=matching.search_candidates(db,CandidateSearchQuery(specialization='backend',grade='middle',skills=['python'],experience_min=3,experience_max=5,salary_min=150000,salary_max=180000))
    assert result.items[0].profile_id==profiles[1].id
    question=Question(specialization_id=1,grade_id=2,type=QuestionType.SINGLE_CHOICE,payload={'text':'Fixture'},correct_answer={'value':'a'})
    db.add(question);db.flush()
    for _ in range(2):
        attempt=TestAttempt(candidate_profile_id=profiles[0].id,specialization_id=1,declared_grade_id=2,target_grade_id=2,status=AttemptStatus.COMPLETED)
        db.add(attempt);db.flush();db.add(TestAnswer(test_attempt_id=attempt.id,question_id=question.id,question_snapshot={},is_correct=True))
    db.flush()
    active=matching.search_candidates(db,CandidateSearchQuery(activity_min=1))
    assert len(active.items)==1 and active.items[0].solved_tasks==1
    assert matching.search_candidates(db,CandidateSearchQuery(fsp=True)).meta.total==1
    db.commit()
    assert client.get('/employer/search?experience_min=8&experience_max=2',headers=auth(e)).status_code==422
    assert client.get('/employer/search?activity_min=1',headers=auth(e)).status_code==200
