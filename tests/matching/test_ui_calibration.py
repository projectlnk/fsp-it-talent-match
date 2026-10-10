from sqlalchemy.orm import Session
from app.modules.auth.models import User
from app.modules.auth.security import hash_password
from app.modules.matching.publication import csrf_token
import pytest

def test_profile_settings_and_legacy_route(client, candidate_headers):
    response = client.get('/candidate/profile', headers=candidate_headers)
    assert response.status_code == 200
    assert 'id="visibility"' in response.text
    assert response.text.count('name="published"') == 1
    assert '<select name="grade" required>' in response.text
    assert client.get('/candidate/search-publication', headers=candidate_headers, follow_redirects=False).headers['location'] == '/candidate/profile#visibility'

def test_successful_cookie_auth_and_failed_login(client, database):
    with Session(database[0]) as session:
        user = session.get(User, database[1]['candidate'].id)
        user.password_hash = hash_password('test1234')
        session.commit()
    email = database[1]['candidate'].email
    failed = client.post('/auth/login', data={'email':email,'password':'wrong'}, follow_redirects=False)
    assert failed.status_code == 401
    assert 'fspcareer_auth_change' not in failed.headers.get('set-cookie', '')
    logged_in = client.post('/auth/login', data={'email':email,'password':'test1234'}, follow_redirects=False)
    assert logged_in.status_code == 303
    assert 'HttpOnly' in logged_in.headers.get_list('set-cookie')[0]
    assert 'fspcareer_auth_change' in logged_in.headers.get('set-cookie', '')
    assert client.get('/candidate/profile').status_code == 200
    assert client.get('/employer/search').status_code == 403
    logged_out = client.post('/auth/logout', follow_redirects=False)
    assert logged_out.status_code == 303
    assert 'fspcareer_auth_change' in logged_out.headers.get('set-cookie', '')
    assert client.get('/candidate/profile').status_code == 401

def test_registration_notice_and_default_privacy(client, database, monkeypatch):
    from app.modules.auth import service
    from app.modules.auth.models import EmailVerificationToken
    from app.modules.candidates.models import CandidateProfile
    from sqlalchemy import select
    EmailVerificationToken.__table__.create(database[0], checkfirst=True)
    monkeypatch.setattr(service, 'send_email', lambda **kwargs: None)
    response = client.post('/auth/register', data={'email':'new@example.com','password':'test1234','role':'candidate','full_name':'New'})
    assert response.status_code == 200
    assert 'По умолчанию ваш профиль скрыт от работодателей' in response.text
    with Session(database[0]) as session:
        user = session.scalar(select(User).where(User.email == 'new@example.com'))
        profile = session.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
        assert profile.is_searchable is False

def test_settings_csrf_and_hidden_access(client, database, headers):
    from app.modules.auth.security import create_access_token
    uid = database[1]['candidate'].id
    client.cookies.set('access_token', create_access_token(uid))
    assert client.post('/candidate/search-publication', data={'published':'yes'}).status_code == 403
    response = client.post('/candidate/search-publication', data={'token':csrf_token(uid)}, follow_redirects=False)
    assert response.headers['location'] == '/candidate/profile?saved=1#visibility'
    assert client.get('/employer/candidates/1', headers=headers).status_code == 404
    assert 'Профиль скрыт от работодателей' in client.get('/candidate/profile').text

def test_legacy_grade_does_not_break_profile(client, database, candidate_headers):
    from app.modules.assessments.models import Grade, Category
    with Session(database[0]) as session:
        category = session.get(Category, database[1]['category'].id)
        grade = session.get(Grade, category.grade_id)
        grade.code = 'legacy-custom'
        grade.name = 'Legacy'
        session.commit()
    response = client.get('/candidate/profile', headers=candidate_headers)
    assert response.status_code == 200
    assert 'Грейд текущей категории: Legacy' in response.text
    assert '<option value="legacy-custom"' not in response.text


@pytest.mark.parametrize('level,expected,status', [('',None,303),('senior','senior',303),('arbitrary',None,400)])
def test_skill_dropdown_save(client, database, candidate_headers, level, expected, status):
    from sqlalchemy import select
    from app.modules.candidates.models import CandidateSkill
    response = client.post('/candidate/profile/skills', headers=candidate_headers,
                           data={'skill':'Dropdown check','level':level}, follow_redirects=False)
    assert response.status_code == status
    with Session(database[0]) as session:
        skill = session.scalar(select(CandidateSkill).where(CandidateSkill.skill == 'Dropdown check'))
        if status == 303:
            assert skill.level == expected
        else:
            assert skill is None
