"""Role entry preserves authentication and account authorization."""
from app.modules.auth.security import hash_password
from tests.matching.test_career_workflows import career


def test_selected_login_role_and_legacy_login(career, client):
    db, employer, candidate, company = career
    password = 'WorkspaceDemo2026'
    for user in (employer, candidate):
        user.password_hash = hash_password(password)
    db.commit()
    for role in ('candidate', 'employer'):
        response = client.get('/auth/login?role=' + role)
        assert response.status_code == 200
        assert f'value="{role}" selected' in response.text
        assert f'/auth/register?role={role}' in response.text
    assert 'value="candidate" selected' in client.get('/auth/login?role=admin').text
    data = {'email': employer.email, 'password': 'wrong', 'role': 'employer',
            'next': '/career/opportunities?archive=true'}
    response = client.post('/auth/login', data=data, follow_redirects=False)
    assert response.status_code == 401
    assert 'value="employer" selected' in response.text
    assert 'archive=true' in response.text and employer.email in response.text
    assert 'set-cookie' not in response.headers
    response = client.post('/auth/login', data={**data, 'password': password, 'role': 'candidate'}, follow_redirects=False)
    assert response.status_code == 400 and 'set-cookie' not in response.headers
    assert 'value="candidate" selected' in response.text
    response = client.post('/auth/login', data={**data, 'password': password, 'role': 'admin'}, follow_redirects=False)
    assert response.status_code == 400 and 'set-cookie' not in response.headers
    for user, role, destination in ((candidate, 'candidate', '/candidate/profile'),
                                    (employer, 'employer', '/employer/profile')):
        response = client.post('/auth/login', data={'email': user.email, 'password': password, 'role': role}, follow_redirects=False)
        assert response.status_code == 303 and response.headers['location'] == destination
        assert 'HttpOnly' in response.headers.get_list('set-cookie')[0]
        client.post('/auth/logout')
    response = client.post('/auth/login', data={'email': candidate.email, 'password': password}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/candidate/profile'
    db.expire_all()
    assert employer.role.value == 'employer' and candidate.role.value == 'candidate'


def test_switch_requires_explicit_confirmation(career, client):
    from app.modules.auth.security import create_access_token
    from app.modules.matching.publication import csrf_token
    db, employer, candidate, company = career
    db.commit()
    for user, target, home in ((candidate,'employer','/candidate/profile'),
                               (employer,'candidate','/employer/profile')):
        client.cookies.set('access_token',create_access_token(user.id))
        response = client.get('/auth/login?role=' + target,follow_redirects=False)
        assert response.status_code == 200 and '/auth/switch-role' in response.text
        assert 'set-cookie' not in response.headers
        assert client.get('/auth/session-state').json()['user_id'] == user.id
        assert client.get('/auth/login?role=' + user.role.value,follow_redirects=False).status_code == 303
        assert client.post('/auth/switch-role',data={'role':target},follow_redirects=False).status_code == 403
        same = client.post('/auth/switch-role',data={'role':user.role.value,'token':csrf_token(user.id)},follow_redirects=False)
        assert same.headers['location'] == home and 'set-cookie' not in same.headers
        switched = client.post('/auth/switch-role',data={'role':target,'token':csrf_token(user.id)},follow_redirects=False)
        assert switched.status_code == 303 and switched.headers['location'] == '/auth/login?role=' + target
        assert 'Max-Age=0' in switched.headers.get_list('set-cookie')[0]
        client.cookies.clear()
        assert 'value="'+target+'" selected' in client.get(switched.headers['location']).text


def test_role_dialog_cancel_keyboard_and_confirm(career, matching_server, browser):
    from playwright.sync_api import expect
    from app.modules.auth.security import create_access_token
    db, employer, candidate, company = career
    db.commit()
    for user, target, label in ((candidate,'employer','Я работодатель'),
                                (employer,'candidate','Я кандидат')):
        context = browser.new_context(viewport={'width':390,'height':900})
        context.add_cookies([{'name':'access_token','value':create_access_token(user.id),'url':matching_server}])
        page = context.new_page();page.goto(matching_server+'/?public=1')
        trigger = page.get_by_role('link',name=label,exact=True)
        trigger.click();dialog=page.locator('[data-role-switch-dialog]')
        expect(dialog).to_be_visible()
        page.keyboard.press('Escape');expect(dialog).not_to_be_visible();expect(trigger).to_be_focused()
        trigger.click();dialog.get_by_role('button',name='Отмена',exact=True).click()
        expect(dialog).not_to_be_visible()
        assert page.request.get(matching_server+'/auth/session-state').json()['user_id']==user.id
        trigger.click();dialog.locator('button[type=submit]').click()
        page.wait_for_url('**/auth/login?role='+target)
        expect(page.locator('select[name=role]')).to_have_value(target)
        assert page.request.get(matching_server+'/auth/session-state').json()['user_id'] is None
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        context.close()
