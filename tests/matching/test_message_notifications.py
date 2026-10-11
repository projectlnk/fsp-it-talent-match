"""Per-dialogue unread cursors do not change activity or participant rights."""
from sqlalchemy import select, func
from app.modules.auth.models import User
from app.modules.auth.security import create_access_token
from app.modules.career import service as s
from app.modules.career.models import ActivityEvent, ThreadReadState
from app.modules.matching.publication import csrf_token
from tests.matching.test_career_workflows import career, accept_invitation


def auth(user):
    return {'Authorization': 'Bearer ' + create_access_token(user.id)}


def test_unread_counts_cursor_scope_and_authorization(career, client):
    db, employer, candidate, company = career
    cid = s.candidate(db, candidate.id).id
    accept_invitation(db, employer, candidate, company)
    first = s.send_message(db, employer, company.id, cid, 'Новые условия')
    second_candidate = db.scalar(select(User).where(User.email == 'candidate-secret-1@example.invalid'))
    second_cid = s.candidate(db, second_candidate.id).id
    accept_invitation(db, employer, second_candidate, company)
    other_message = s.send_message(db, employer, company.id, second_cid, 'Другая переписка')
    db.commit()
    count = lambda user: client.get('/career/message-notifications', headers=auth(user)).json()['count']
    assert count(candidate) == 2  # invitation + ordinary incoming message
    assert count(employer) == 2  # one automatic acceptance per counterpart
    assert count(second_candidate) == 2
    url = f'/career/threads/{company.id}/{cid}/read'
    before = db.scalar(select(func.count(ActivityEvent.id)));db.commit()
    assert client.post(url, headers=auth(candidate), data={'last_message':first.id}).status_code == 403
    outsider = db.scalar(select(User).where(User.email == 'candidate-secret-2@example.invalid'));db.commit()
    assert client.post(url, headers=auth(outsider), data={'token':csrf_token(outsider.id),'last_message':first.id}).status_code == 404
    assert count(outsider) == 0
    assert client.get('/career/message-notifications').status_code == 401
    data = {'token':csrf_token(candidate.id),'last_message':first.id}
    assert client.post(url, headers=auth(candidate), data={**data,'last_message':other_message.id}).status_code == 422
    response = client.post(url, headers=auth(candidate), data=data)
    assert response.status_code == 200 and response.json()['last_read'] == first.id
    assert count(candidate) == 0 and count(second_candidate) == 2
    assert count(employer) == 2
    assert client.post(url, headers=auth(candidate), data=data).json()['last_read'] == first.id
    assert client.post(url, headers=auth(candidate), data={**data,'last_message':0}).status_code == 200
    db.expire_all()
    assert db.get(ThreadReadState,(candidate.id,company.id,cid)).last_message_id == first.id
    assert db.scalar(select(func.count(ActivityEvent.id))) == before
    s.consent(db, candidate.id, 'processing', False);db.commit()
    assert count(candidate) == 0 and count(employer) == 1
    assert client.post(url, headers=auth(candidate), data=data).status_code == 404


def test_live_badges_for_both_roles(career, matching_server, browser):
    from playwright.sync_api import expect
    db, employer, candidate, company = career
    cid = s.candidate(db, candidate.id).id
    accept_invitation(db, employer, candidate, company)
    db.commit()
    contexts = []
    pages = []
    for user in (candidate, employer):
        context = browser.new_context(viewport={'width':390,'height':900})
        context.add_cookies([{'name':'access_token','value':create_access_token(user.id),'url':matching_server}])
        contexts.append(context)
        page = context.new_page();pages.append(page)
        page.goto(matching_server + f'/career/threads/{company.id}/{cid}')
        expect(page.locator('[data-message-badge]')).to_be_hidden(timeout=12000)
    for page, author, reader in ((pages[0],employer,candidate),(pages[1],candidate,employer)):
        page.goto(matching_server + ('/candidate/profile' if reader == candidate else '/employer/profile'))
        s.send_message(db,author,company.id,cid,'Проверка новых сообщений');db.commit()
        expect(page.locator('[data-message-badge]')).to_be_visible(timeout=12000)
        expect(page.locator('[data-message-badge]')).to_have_text('1')
        page.goto(matching_server + f'/career/threads/{company.id}/{cid}')
        expect(page.locator('[data-message-badge]')).to_be_hidden(timeout=12000)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    for context in contexts:context.close()
