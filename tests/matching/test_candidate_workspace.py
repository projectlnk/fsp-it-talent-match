"""Focused checks for candidate presentation and public vacancy extension."""
from datetime import UTC, datetime, timedelta
import re
import pytest
from sqlalchemy import select,func
from app.modules.auth.models import User
from app.modules.auth.security import create_access_token,hash_password
from app.modules.assessments import service as assessment
from app.modules.assessments.models import TestAttempt,TestAnswer,Question,QuestionType,AttemptStatus
from app.modules.employers.models import Offer,OfferStatus
from app.modules.career import service as career_service
from app.modules.matching.publication import csrf_token
from test_career_workflows import career,job


def auth(user):return {'Authorization':'Bearer '+create_access_token(user.id)}


def test_navigation_profile_sections_and_company_links(career,client):
    db,e,c,company=career
    vacancy=job(db,e)
    cid=career_service.candidate(db,c.id).id
    db.add(Offer(employer_profile_id=company.id,candidate_profile_id=cid,title='Входящее приглашение',salary_from=1,salary_to=2,status=OfferStatus.SENT));db.commit()
    response=client.get('/candidate/profile',headers=auth(c));assert response.status_code==200
    aside=response.text.split('<aside class="sidebar">')[1].split('</aside>')[0]
    assert [re.sub(r'<[^>]+>', '', body).strip() for body in re.findall(r'<a[^>]*>(.*?)</a>', aside, re.S)]==['Мой профиль','Тесты','Вакансии','Работодатели','Связь']
    assert re.search(r'\b1\s+ожидают ответа', re.sub(r'<[^>]+>', ' ', response.text)) and 'data-resume-dialog' in response.text
    for url in ['/candidate/profile?tab=fsp','/candidate/profile?tab=settings','/candidate/offers','/career/connections','/career/meetings','/career/applications']:
        assert client.get(url,headers=auth(c)).status_code==200,url
    assert 'тестовый реестр' in client.get('/candidate/profile?tab=fsp',headers=auth(c)).text
    assert 'name="processing"' in client.get('/candidate/profile?tab=settings',headers=auth(c)).text
    assert f'/career/companies/{company.id}' in client.get('/career/leaderboard',headers=auth(c)).text
    assert client.get('/candidate/profile',headers=auth(e)).status_code==403
    assert 'Мой профиль' in client.get('/',headers=auth(c)).text


def test_recommendation_progress_finish_and_owner(career,client):
    db,e,c,company=career
    for i in range(10):db.add(Question(specialization_id=1,grade_id=2,type=QuestionType.SINGLE_CHOICE,payload={'text':f'Question {i}','options':['a','b']},correct_answer={'value':'a'}))
    db.commit()
    before=db.scalar(select(func.count(TestAttempt.id)))
    r=client.get('/assessments?specialization=backend&grade=middle',headers=auth(c));assert r.status_code==200 and 'Начать тест' in r.text
    assert db.scalar(select(func.count(TestAttempt.id)))==before
    attempt=assessment.start_attempt(db,user_id=c.id,specialization_code='backend',grade_code='middle')
    assert assessment.start_attempt(db,user_id=c.id,specialization_code='backend',grade_code='middle').id==attempt.id
    other=db.scalar(select(User).where(User.email=='candidate-secret-1@example.invalid'))
    with pytest.raises(assessment.AttemptNotFound):
        assessment.get_attempt(db,attempt_id=attempt.id,user_id=other.id)
    answer=attempt.answers[0]
    assessment.submit_answer(db,user_id=c.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload={'value':'a'})
    r=client.get('/assessments?tab=progress',headers=auth(c));assert 'Сохранено ответов: 1 из 10' in r.text
    assert f'/assessments/attempt/{attempt.id}' in r.text
    assert client.get(f'/assessments/attempt/{attempt.id}',headers=auth(e)).status_code==403
    assert client.get('/assessments?tab=recommended',headers=auth(c)).status_code==200
    state=assessment.attempt_public_state(assessment.get_attempt(db,attempt_id=attempt.id,user_id=c.id))
    assert not any('is_correct' in q or 'correct_answer' in q['question'] for q in state['questions'])
    for answer in attempt.answers[1:]:assessment.submit_answer(db,user_id=c.id,attempt_id=attempt.id,answer_id=answer.id,answer_payload={'value':'a'})
    assessment.finish_attempt(db,user_id=c.id,attempt_id=attempt.id)
    count=db.scalar(select(func.count(TestAttempt.id)))
    with pytest.raises(assessment.AttemptAlreadyCompleted):
        assessment.finish_attempt(db,user_id=c.id,attempt_id=attempt.id)
    assert db.scalar(select(func.count(TestAttempt.id)))==count
    db.commit()
    assert f'/assessments/attempt/{attempt.id}' not in client.get('/assessments?tab=progress',headers=auth(c)).text
    assert f'/assessments/attempt/{attempt.id}/result' in client.get('/assessments?tab=results',headers=auth(c)).text


def test_public_catalog_scope_application_and_safe_return(career,client):
    db,e,c,company=career;vacancy=job(db,e);db.commit()
    response=client.get('/career/opportunities');assert response.status_code==200 and vacancy.title in response.text
    assert client.get(f'/career/opportunities/{vacancy.id}').status_code==200
    assert client.post(f'/career/opportunities/{vacancy.id}/apply',data={'share_contacts':'yes'}).status_code==401
    assert client.get(f'/career/companies/{company.id}').status_code==200
    e.is_email_verified=False;db.commit()
    assert client.get('/career/opportunities',headers=auth(e)).status_code==403
    assert client.get(f'/career/opportunities/{vacancy.id}',headers=auth(e)).status_code==403
    e.is_email_verified=True;db.commit()
    career_service.apply(db,c.id,vacancy.id,'Уже отправлен');db.commit()
    r=client.get(f'/career/opportunities/{vacancy.id}?return_to=//evil.test/career/opportunities',headers=auth(c))
    assert 'Ваш отклик' in r.text and 'action="/career/opportunities/' not in r.text and 'href="//evil' not in r.text
    assert c.email not in client.get(f'/career/companies/{company.id}').text
    career_service.change_opportunity(db,e.id,vacancy.id,'close');db.commit()
    assert vacancy.title not in client.get('/career/opportunities').text
    assert client.get(f'/career/opportunities/{vacancy.id}').status_code==404
    assert client.get(f'/career/opportunities/{vacancy.id}',headers=auth(e)).status_code==200


def test_candidate_login_default_destination(career,client):
    db,e,c,company=career;c.password_hash=hash_password('WorkspaceDemo2026');db.commit()
    r=client.post('/auth/login',data={'email':c.email,'password':'WorkspaceDemo2026'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/candidate/profile'
    r=client.post('/auth/login',data={'email':c.email,'password':'WorkspaceDemo2026','next':'/assessments?tab=results'},follow_redirects=False)
    assert r.headers['location']=='/assessments?tab=results'


def test_pdf_preview_delegates_to_same_owner_generator(career,client,monkeypatch):
    db,e,c,company=career
    from app.modules.candidates import resume
    calls=[]
    def generate(session,*,user_id):
        calls.append(user_id)
        return b'%PDF-fixture'
    monkeypatch.setattr(resume,'generate_resume_pdf',generate)
    inline=client.get('/candidate/profile/resume.pdf?preview=true',headers=auth(c))
    download=client.get('/candidate/profile/resume.pdf',headers=auth(c))
    assert inline.headers['content-disposition'].startswith('inline;')
    assert download.headers['content-disposition'].startswith('attachment;')
    assert calls==[c.id,c.id]
    assert client.get('/candidate/profile/resume.pdf?preview=true',headers=auth(e)).status_code==403
    assert calls==[c.id,c.id]


def test_candidate_home_until_logout(career,client):
    db,e,c,company=career
    c.password_hash=hash_password('WorkspaceDemo2026');db.commit()
    client.post('/auth/login',data={'email':c.email,'password':'WorkspaceDemo2026'})
    for _ in range(2):
        response=client.get('/',follow_redirects=False)
        assert response.status_code==303 and response.headers['location']=='/candidate/profile'
        assert response.headers['cache-control']=='no-store'
    response=client.get('/')
    assert 'Мой профиль' in response.text and 'Я работодатель' not in response.text
    client.post('/auth/logout')
    response=client.get('/')
    assert response.status_code==200 and 'Я работодатель' in response.text
    assert '<aside class="sidebar">' not in response.text
