"""Read-only feeds preserve participant checks and do not reward polling."""
from sqlalchemy import select,func
from app.modules.auth.security import create_access_token
from app.modules.auth.models import User
from app.modules.career.models import ActivityEvent,ThreadMessage
from app.modules.career import service as s
from test_career_workflows import career,job,accept_invitation


def auth(user):return {'Authorization':'Bearer '+create_access_token(user.id)}


def test_live_feed_both_roles_cursor_and_revocation(career,client):
    db,e,c,company=career;vacancy=job(db,e);s.apply(db,c.id,vacancy.id,'Отклик');cid=s.candidate(db,c.id).id
    accept_invitation(db,e,c,company)
    first=s.send_message(db,e,company.id,cid,'Первое сообщение')
    second=s.send_message(db,c,company.id,cid,'Ответ кандидата <script>unsafe</script>');db.commit()
    before=db.scalar(select(func.count(ActivityEvent.id)))
    url=f'/career/threads/{company.id}/{cid}/messages'
    for user,own in [(e,False),(c,True)]:
        response=client.get(url+f'?after={first.id}',headers=auth(user))
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        messages=response.json()['messages'];assert len(messages)==1 and messages[0]['id']==second.id and messages[0]['own']==own
    assert client.get(url+f'?after={second.id}',headers=auth(e)).json()['messages']==[]
    assert db.scalar(select(func.count(ActivityEvent.id)))==before
    other=db.scalar(select(User).where(User.email=='candidate-secret-1@example.invalid'));other.is_email_verified=True;db.commit()
    assert client.get(url,headers=auth(other)).status_code==404
    assert client.get(url).status_code==401
    s.consent(db,c.id,'processing',False);db.commit()
    assert client.get(url,headers=auth(e)).status_code==404
    assert client.get(url,headers=auth(c)).status_code==404
