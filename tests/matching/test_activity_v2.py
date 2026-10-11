"""Focused checks for the agreed two-limit rating and invitation-led workflow."""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.modules.career import service as s
from app.modules.career.models import ThreadMessage, Meeting, ActivityEvent, Application
from app.modules.career.schemas import MeetingInput
from app.modules.employers import service as offers
from app.modules.employers.schemas import OfferCreate
from app.modules.auth.security import create_access_token
from tests.matching.test_career_workflows import career, job


def accept(db,e,c,company,opportunity=None):
    cid=s.candidate(db,c.id).id
    offer=offers.create_offer(db,employer_user_id=e.id,payload=OfferCreate(candidate_profile_id=cid,
        opportunity_id=opportunity.id if opportunity else None,title='Обсудить работу',description='Условия обсуждения',
        salary_from=100000,salary_to=200000,contact_method='Чат'))
    offers.respond_to_offer(db,offer_id=offer.id,candidate_user_id=c.id,decision='accepted')
    return cid,offer


def test_invitation_technical_messages_and_single_live_reward(career,client):
    db,e,c,company=career;row=job(db,e);s.apply(db,c.id,row.id,'Отклик');cid=s.candidate(db,c.id).id
    assert not s.accepted_pair(db,company.id,cid)
    with pytest.raises(HTTPException):s.send_message(db,e,company.id,cid,'Без согласия')
    db.commit()
    assert client.get(f'/career/applicants/1',headers={'Authorization':'Bearer '+create_access_token(e.id)}).status_code==200
    cid,offer=accept(db,e,c,company,row)
    offers.respond_to_offer(db,offer_id=offer.id,candidate_user_id=c.id,decision='accepted')
    assert db.scalar(select(func.count(ThreadMessage.id)))==2
    assert s.leaderboard(db)[0]['score']==0
    s.send_message(db,e,company.id,cid,'Здравствуйте')
    assert s.leaderboard(db)[0]['score']==0
    s.send_message(db,c,company.id,cid,'Добрый день')
    assert s.leaderboard(db)[0]['score']==1
    s.send_message(db,c,company.id,cid,'Ещё сообщение')
    assert s.leaderboard(db)[0]['score']==1
    assert db.scalar(select(func.count(ActivityEvent.id)).where(ActivityEvent.kind=='interaction_v2'))==1
    db.commit()
    html=client.get(f'/career/threads/{company.id}/{cid}',headers={'Authorization':'Bearer '+create_access_token(e.id)})
    assert html.status_code==200 and html.text.count('data-technical-message')==2
    assert client.get(f'/career/applicants/1',headers={'Authorization':'Bearer '+create_access_token(c.id)}).status_code==403


def test_meeting_mutual_confirmation_cancel_and_hire(career,monkeypatch):
    db,e,c,company=career;row=job(db,e);cid,_=accept(db,e,c,company,row)
    start=s.now(db)
    meeting=s.schedule(db,e.id,cid,MeetingInput(scheduled_at=start+timedelta(days=1),timezone='UTC',channel='Видеовстреча'))
    assert meeting.opportunity_id==row.id
    assert s.leaderboard(db)[0]['score']==2
    s.update_meeting(db,e,meeting.id,cancel=True)
    assert s.leaderboard(db)[0]['score']==0
    meeting=s.schedule(db,e.id,cid,MeetingInput(scheduled_at=start+timedelta(days=1),timezone='UTC',channel='Видеовстреча'))
    monkeypatch.setattr(s,'now',lambda db:start+timedelta(days=2))
    s.meeting_action(db,c,meeting.id,'interview')
    assert not meeting.interview_confirmed_at
    s.meeting_action(db,e,meeting.id,'interview')
    assert meeting.interview_confirmed_at and s.leaderboard(db)[0]['score']==10
    s.meeting_action(db,e,meeting.id,'hire')
    monkeypatch.setattr(s,'now',lambda db:start+timedelta(days=20))
    s.process_due(db)
    assert meeting.status=='confirmed' and s.leaderboard(db)[0]['closed_vacancies']==0
    s.meeting_action(db,c,meeting.id,'hire');s.meeting_action(db,c,meeting.id,'hire')
    rating=s.leaderboard(db)[0]
    assert rating['score']==10 and rating['closed_vacancies']==1 and rating['score_limit']==300
    assert row.status=='inactive'
    with pytest.raises(HTTPException):s.change_opportunity(db,e.id,row.id,'restore')


def test_auto_confirmation_is_only_for_meeting(career,monkeypatch):
    db,e,c,company=career;row=job(db,e);cid,_=accept(db,e,c,company,row)
    start=s.now(db);meeting=s.schedule(db,e.id,cid,MeetingInput(scheduled_at=start+timedelta(days=1),channel='Встреча'))
    monkeypatch.setattr(s,'now',lambda db:start+timedelta(days=2))
    s.meeting_action(db,e,meeting.id,'interview')
    monkeypatch.setattr(s,'now',lambda db:start+timedelta(days=4))
    s.process_due(db);s.process_due(db)
    assert meeting.interview_confirmed_at and not meeting.candidate_hire_at
    assert s.leaderboard(db)[0]['score']==10 and s.leaderboard(db)[0]['closed_vacancies']==0


def test_both_limits_and_no_legacy_bonus(career,monkeypatch):
    db,e,c,company=career;cid,_=accept(db,e,c,company)
    monkeypatch.setattr(s,'rewarded_conversations',lambda db,eid:set(range(1000)))
    start=s.now(db)
    s.event(db,company.id,'old-profile','profile',5,'Исторический бонус')
    for i in range(30):
        db.add(Meeting(employer_id=company.id,candidate_id=cid,scheduled_at=start-timedelta(days=3),
            timezone='UTC',channel='Фикстура',status='confirmed',interview_confirmed_at=start))
    db.flush()
    rating=s.leaderboard(db)[0]
    assert rating['chat_limit']==160 and rating['chat_points']==160
    assert rating['raw_score']==460 and rating['score']==200
    assert rating['closed_vacancies']==0
    assert s.leaderboard(db)[0]['score']==200


@pytest.mark.parametrize('total,viewed,expected',[(0,0,0),(5,5,5),(50,39,39),(50,40,80),(50,50,100),(200,40,40),(200,100,100),(10000,2000,100)])
def test_vacancy_normalization(total,viewed,expected):
    assert s.normalized_activity(total,viewed)==expected


def test_view_is_scoped_to_application_and_catalog_order(career,client):
    db,e,c,company=career;first=job(db,e)
    second=s.save_opportunity(db,e.id,'vacancy',__import__('tests.matching.test_career_workflows',fromlist=['payload']).payload().model_copy(update={'title':'Новая вакансия'}))
    a=s.apply(db,c.id,first.id,'Отклик');s.apply(db,c.id,second.id,'Другой отклик');db.commit()
    headers={'Authorization':'Bearer '+create_access_token(e.id)}
    for _ in range(2):assert client.get(f'/career/applicants/{a.id}',headers=headers).status_code==200
    db.expire_all()
    assert s.vacancy_metrics(db,first.id)['viewed']==1 and s.vacancy_metrics(db,second.id)['viewed']==0
    response=client.get('/career/opportunities')
    assert response.status_code==200
    assert response.text.index(first.title)<response.text.index(second.title)


def test_archived_vacancy_history_and_legacy_thread_are_private(career,client):
    db,e,c,company=career;row=job(db,e);application=s.apply(db,c.id,row.id,'Отклик');cid=s.candidate(db,c.id).id
    # Real historic data are preserved; a fresh application is not silently promoted to an accepted offer.
    db.add(ThreadMessage(employer_id=company.id,candidate_id=cid,author_id=e.id,body='Старая история',created_at=s.now(db),kind='message'))
    s.change_opportunity(db,e.id,row.id,'close');db.commit()
    assert client.get(f'/career/opportunities/{row.id}').status_code==404
    assert client.get(f'/career/opportunities/{row.id}',headers={'Authorization':'Bearer '+create_access_token(c.id)}).status_code==200
    response=client.get(f'/career/threads/{company.id}/{cid}',headers={'Authorization':'Bearer '+create_access_token(e.id)})
    assert response.status_code==200 and 'Старая история' in response.text and 'name="body"' not in response.text
    with pytest.raises(HTTPException):s.send_message(db,e,company.id,cid,'Новая переписка без приглашения')
    assert s.leaderboard(db)[0]['score']==0
