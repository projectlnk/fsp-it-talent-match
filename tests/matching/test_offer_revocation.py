"""Withdrawal is owner-only, idempotent, and closes live composition."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.modules.career import service as s
from app.modules.career.models import ThreadMessage
from app.modules.employers import service as offers
from app.modules.employers.schemas import OfferCreate
from app.modules.employers.models import EmployerProfile
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import create_access_token
from app.modules.matching.publication import csrf_token
from tests.matching.test_career_workflows import career
from tests.matching.test_activity_v2 import accept


def auth(user):
    return {'Authorization':'Bearer '+create_access_token(user.id)}


def test_withdraw_preserves_history_reward_and_stops_both_roles(career, client):
    db,e,c,company=career;cid,offer=accept(db,e,c,company)
    s.send_message(db,e,company.id,cid,'Рабочий вопрос')
    s.send_message(db,c,company.id,cid,'Рабочий ответ');db.commit()
    assert s.leaderboard(db)[0]['score']==1
    withdrawn=offers.revoke_offer(db,offer_id=offer.id,employer_user_id=e.id)
    assert withdrawn.status=='revoked' and withdrawn.revoked_at and withdrawn.contacts is None
    offers.revoke_offer(db,offer_id=offer.id,employer_user_id=e.id)
    notice=db.scalars(select(ThreadMessage).where(ThreadMessage.kind=='revocation')).one()
    assert notice.body=='Приглашение отозвано' and notice.author_id==e.id
    assert s.leaderboard(db)[0]['score']==1
    assert not s.accepted_pair(db,company.id,cid)
    for user in (e,c):
        with pytest.raises(HTTPException) as error:s.send_message(db,user,company.id,cid,'Запрещённое')
        assert error.value.status_code==403
    with pytest.raises(offers.InvalidStatusTransition):
        offers.respond_to_offer(db,offer_id=offer.id,candidate_user_id=c.id,decision='accepted')
    db.commit()
    for user in (e,c):
        page=client.get(f'/career/threads/{company.id}/{cid}',headers=auth(user))
        assert page.status_code==200 and 'Приглашение отозвано' in page.text
        feed=client.get(f'/career/threads/{company.id}/{cid}/messages',headers=auth(user)).json()
        assert not feed['can_send'] and feed['messages'][-1]['technical']
        assert client.post(f'/career/threads/{company.id}/{cid}',headers=auth(user),
            data={'token':csrf_token(user.id),'body':'Запрещённое'}).status_code==403
    assert 'candidate-secret-0@example.invalid' not in client.get(
        f'/career/threads/{company.id}/{cid}',headers=auth(e)).text
    assert client.get(f'/candidate/offers/{offer.id}',headers=auth(c)).status_code==200


def test_pending_withdraw_has_no_reward_and_owner_csrf_guards(career,client):
    db,e,c,company=career;cid=s.candidate(db,c.id).id
    offer=offers.create_offer(db,employer_user_id=e.id,payload=OfferCreate(candidate_profile_id=cid,
        title='Приглашение',salary_from=1,salary_to=2))
    other=User(email='other-hr@example.invalid',password_hash='unused',role=UserRole.EMPLOYER,is_email_verified=True)
    db.add(other);db.flush();db.add(EmployerProfile(user_id=other.id,company_name='Другая компания'));db.commit()
    url=f'/employer/offers/{offer.id}/revoke'
    assert client.post(url,headers=auth(e)).status_code==403
    assert client.post(url,headers=auth(other),data={'token':csrf_token(other.id)}).status_code==404
    assert client.post(url,headers=auth(c),data={'token':csrf_token(c.id)}).status_code==403
    assert client.post(url,headers=auth(e),data={'token':csrf_token(e.id)},follow_redirects=False).status_code==303
    assert client.post('/api/v1/employers/offers/'+str(offer.id)+'/revoke',headers=auth(e)).status_code==200
    db.expire_all()
    assert db.scalar(select(func.count(ThreadMessage.id)).where(ThreadMessage.kind=='revocation'))==1
    assert s.leaderboard(db)[0]['score']==0
    db.commit()
    html=client.get('/employer/offers',headers=auth(e)).text
    assert 'href="/employer/offers" class="active" aria-current="page"' in html and 'отозвано' in html.lower()
    chat=client.get('/career/connections',headers=auth(e)).text
    assert '<h2>Исходящие приглашения</h2>' not in chat


def test_old_acceptance_does_not_reopen_until_new_explicit_acceptance(career):
    db,e,c,company=career;cid,first=accept(db,e,c,company);cid,second=accept(db,e,c,company)
    offers.revoke_offer(db,offer_id=first.id,employer_user_id=e.id)
    assert not s.accepted_pair(db,company.id,cid)
    with pytest.raises(offers.InvalidStatusTransition):
        offers.respond_to_offer(db,offer_id=first.id,candidate_user_id=c.id,decision='accepted')
    accept(db,e,c,company)
    assert s.accepted_pair(db,company.id,cid)


def test_live_withdrawal_in_chromium(career, matching_server, browser):
    from playwright.sync_api import expect
    db,e,c,company=career;cid,offer=accept(db,e,c,company);db.commit()
    contexts=[];errors=[]
    try:
        for user in (e,c):
            ctx=browser.new_context(viewport={'width':1440,'height':900})
            ctx.add_cookies([{'name':'access_token','value':create_access_token(user.id),'url':matching_server}])
            contexts.append(ctx)
        employer=contexts[0].new_page();candidate=contexts[1].new_page()
        for page in (employer,candidate):page.on('pageerror',lambda error:errors.append(str(error)))
        thread=f'/career/threads/{company.id}/{cid}'
        candidate.goto(matching_server+thread)
        expect(candidate.locator('[data-chat-compose]')).to_be_visible()
        employer.goto(matching_server+'/career/connections')
        tabs=employer.locator('.section-tabs a')
        assert tabs.all_text_contents()==['Чаты','Календарь','Исходящие приглашения']
        employer.get_by_role('link',name='Исходящие приглашения',exact=True).click()
        expect(employer.locator('.section-tabs a.active')).to_have_text('Исходящие приглашения')
        employer.reload()
        employer.get_by_role('button',name='Отозвать приглашение',exact=True).click()
        expect(candidate.locator('[data-chat-feed]')).to_contain_text('Приглашение отозвано',timeout=10000)
        expect(candidate.locator('[data-chat-compose]')).to_be_hidden()
        expect(candidate.locator('[data-chat-closed]')).to_be_visible()
        assert candidate.locator('[data-chat-feed]').get_by_text('Приглашение отозвано',exact=True).count()==1
        candidate.reload()
        expect(candidate.locator('[data-chat-compose]')).to_have_count(0)
        employer.set_viewport_size({'width':390,'height':844})
        for path in ['/employer/offers','/career/connections','/career/meetings']:
            employer.goto(matching_server+path)
            assert employer.evaluate('document.documentElement.scrollWidth<=innerWidth'),path
        assert not errors,errors
    finally:
        for ctx in contexts:ctx.close()
