from app.modules.auth.security import create_access_token, hash_password
from tests.matching.test_career_workflows import career


def test_html_auth_failure_redirects_but_api_keeps_401(career,client):
    db,e,c,company=career
    r=client.get('/candidate/profile',headers={'Accept':'text/html'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location']=='/auth/session-refresh'
    r=client.get('/auth/session-refresh',follow_redirects=False)
    assert r.headers['location']=='/'
    assert client.get('/api/v1/candidates/me').status_code==401
    r=client.get('/candidate/profile',headers={'Accept':'text/html','Authorization':'Bearer '+create_access_token(e.id)},follow_redirects=False)
    assert r.status_code==303
    r=client.get('/auth/session-refresh',headers={'Authorization':'Bearer '+create_access_token(e.id)},follow_redirects=False)
    assert r.headers['location']=='/employer/profile'


def test_both_roles_home_logo_and_session_identity(career,client):
    db,e,c,company=career
    for user,path,label in [(c,'/candidate/profile','Кабинет кандидата'),(e,'/employer/profile','Кабинет работодателя')]:
        headers={'Authorization':'Bearer '+create_access_token(user.id)}
        assert client.get('/',headers=headers,follow_redirects=False).headers['location']==path
        public=client.get('/?public=1',headers=headers)
        assert public.status_code==200 and 'Я работодатель' in public.text and label in public.text
        assert 'href="/?public=1"' in public.text and user.email in public.text
        assert client.get('/auth/session-state',headers=headers).json()=={'user_id':user.id}
        user.password_hash=hash_password('WorkspaceDemo2026');db.commit()
        login=client.post('/auth/login',data={'email':user.email,'password':'WorkspaceDemo2026'},follow_redirects=False)
        assert login.headers['location']==path
        client.post('/auth/logout')
    assert client.get('/auth/session-state').json()=={'user_id':None}
