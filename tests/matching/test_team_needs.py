"""Saved filters delegate to ordinary ranking; application path stays intact."""
import re
from urllib.parse import parse_qs, urlsplit
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.modules.auth.models import User, UserRole
from app.modules.auth.security import create_access_token
from app.modules.employers.models import EmployerProfile
from app.modules.career.models import TeamNeedTemplate, TeamNeedPosition, Application
from app.modules.career import service as career_service
from app.modules.matching import needs, service
from app.modules.matching.schemas import CandidateSearchQuery, TeamNeedInput
from app.modules.matching.publication import csrf_token
from tests.matching.test_career_workflows import career, job


def auth(user):
    return {'Authorization': 'Bearer '+create_access_token(user.id)}


def test_template_ownership_validation_and_same_ranking(career, client):
    db,e,c,company=career
    payload=TeamNeedInput(name='Команда нового проекта',positions=[
        {'name':'Backend Middle','filters':{'specialization':'backend','grade':'middle','skills':['Python'],'work_format':'remote'}},
        {'name':'API Middle','filters':{'specialization':'backend','grade':'middle','skills':['Python']}},
        {'name':'Frontend Junior','filters':{'specialization':'frontend','grade':'junior'}}])
    template=needs.save_template(db,e.id,payload);db.commit();tid=template.id
    _,groups=needs.search_groups(db,e.id,tid,{'page_size':'1'})
    for group in groups:
        ordinary=service.search_candidates(db,group['filters'])
        assert group['result'].model_dump()==ordinary.model_dump()
        assert 'page' not in group['position'].filters and 'page_size' not in group['position'].filters
    assert groups[0]['result'].items[0].profile_id==groups[1]['result'].items[0].profile_id
    _,second=needs.search_groups(db,e.id,tid,{f'position_page_{groups[0]["position"].id}':'2','page_size':'1'})
    assert second[0]['result'].meta.page==2 and second[1]['result'].meta.page==1
    db.commit()
    response=client.get(f'/employer/search?need_id={tid}',headers=auth(e))
    assert response.status_code==200 and all(p['name'] in response.text for p in payload.model_dump()['positions'])
    assert 'secret-contact@example.invalid' not in response.text
    assert client.get(f'/employer/search?need_id={tid}',headers=auth(c)).status_code==403
    outsider=User(email='need-outsider@example.invalid',password_hash='unused',role=UserRole.EMPLOYER,is_email_verified=True)
    db.add(outsider);db.flush();db.add(EmployerProfile(user_id=outsider.id,company_name='Другая'));db.commit()
    for path in [f'/employer/search?need_id={tid}',f'/employer/team-needs/{tid}/edit']:
        assert client.get(path,headers=auth(outsider)).status_code==404
    assert client.post(f'/employer/team-needs/{tid}/delete',headers=auth(outsider),data={'token':csrf_token(outsider.id)}).status_code==404
    form={'name':'Сохранённый шаблон','position_index':'0','position_0_name':'Backend','position_0_specialization':'backend',
          'position_0_grade':'middle','position_0_skills':'Python, SQL','position_0_all_skills':'true',
          'position_0_experience_min':'2','position_0_experience_max':'5','position_0_salary_min':'100000',
          'position_0_salary_max':'200000','position_0_fsp':'false','position_0_location':'Москва',
          'position_0_work_format':'remote','position_0_test_score_min':'75','position_0_activity_min':'1',
          'position_0_query':'разработчик','position_0_desired_role':'Backend'}
    assert client.post('/employer/team-needs',headers=auth(e),data=form).status_code==403
    form['token']=csrf_token(e.id)
    assert client.post('/employer/team-needs',headers=auth(e),data={**form,'position_0_experience_max':'1'}).status_code==422
    assert client.post('/employer/team-needs',headers=auth(e),data={**form,'position_0_grade':'invented'}).status_code==422
    created=client.post('/employer/team-needs',headers=auth(e),data=form,follow_redirects=False)
    assert created.status_code==303
    new_id=int(parse_qs(urlsplit(created.headers['location']).query)['saved'][0])
    db.expire_all();saved=needs.get_template(db,e.id,new_id)
    assert saved.positions[0].filters==CandidateSearchQuery(specialization='backend',grade='middle',skills=['python','sql'],
        all_skills=True,experience_min=2,experience_max=5,salary_min=100000,salary_max=200000,fsp=False,
        location='Москва',work_format='remote',test_score_min=75,activity_min=1,query='разработчик',desired_role='Backend').model_dump(mode='json',exclude={'page','page_size'})
    db.commit()
    assert client.post(f'/employer/team-needs/{new_id}/edit',headers=auth(e),data={**form,'name':'Изменённый шаблон'},follow_redirects=False).status_code==303
    assert client.post(f'/employer/team-needs/{new_id}/delete',headers=auth(e),data={'token':csrf_token(e.id)},follow_redirects=False).status_code==303
    db.expire_all();assert db.get(TeamNeedTemplate,new_id) is None
    assert not db.scalar(select(TeamNeedPosition.id).where(TeamNeedPosition.template_id==new_id))


def test_candidate_application_received_by_owner(career, client):
    db,e,c,company=career;vacancy=job(db,e);oid=vacancy.id;db.commit()
    assert client.get(f'/career/opportunities/{oid}').status_code==200
    response=client.get(f'/career/opportunities/{oid}',headers=auth(c))
    assert 'Отправить отклик' in response.text
    data={'token':csrf_token(c.id),'message':'Хочу обсудить вакансию','share_contacts':'yes'}
    assert client.post(f'/career/opportunities/{oid}/apply',headers=auth(c),data={**data,'share_contacts':''}).status_code==422
    for _ in range(2):
        r=client.post(f'/career/opportunities/{oid}/apply',headers=auth(c),data=data,follow_redirects=False)
        assert r.status_code==303 and r.headers['location'].startswith('/career/applications')
    received=client.get(f'/career/applications?oid={oid}',headers=auth(e))
    assert received.status_code==200 and 'Хочу обсудить вакансию' in received.text
    own=client.get('/career/applications',headers=auth(c));assert 'Хочу обсудить вакансию' in own.text
    db.expire_all();assert db.scalar(select(func.count(Application.id)).where(Application.opportunity_id==oid))==1
    aid=db.scalar(select(Application.id).where(Application.opportunity_id==oid));db.commit()
    assert client.get(f'/career/applicants/{aid}',headers=auth(e)).status_code==200
    assert client.get(f'/career/applicants/{aid}',headers=auth(c)).status_code==403
    outsider=User(email='application-outsider@example.invalid',password_hash='unused',role=UserRole.EMPLOYER,is_email_verified=True)
    db.add(outsider);db.flush();db.add(EmployerProfile(user_id=outsider.id,company_name='Другая'));db.commit()
    assert client.get(f'/career/applications?oid={oid}',headers=auth(outsider)).status_code==404
    assert client.get(f'/career/applicants/{aid}',headers=auth(outsider)).status_code==404


def test_browser_template_positions_selection_and_return(career, matching_server, browser):
    from playwright.sync_api import expect
    db,e,c,company=career;db.commit()
    context=browser.new_context(viewport={'width':1440,'height':1000})
    context.add_cookies([{'name':'access_token','value':create_access_token(e.id),'url':matching_server}])
    page=context.new_page();page.goto(matching_server+'/employer/team-needs/new')
    page.locator('[name=name]').fill('Команда нового проекта')
    first=page.locator('[data-need-position]').nth(0)
    first.locator('input[name$="_name"]').fill('Backend Middle')
    first.locator('select[name$="_specialization"]').select_option('backend')
    first.locator('select[name$="_grade"]').select_option('middle')
    page.get_by_role('button',name='Добавить позицию',exact=True).click()
    second=page.locator('[data-need-position]').nth(1)
    second.locator('input[name$="_name"]').fill('Frontend Junior')
    second.locator('select[name$="_specialization"]').select_option('frontend')
    second.locator('select[name$="_grade"]').select_option('junior')
    page.get_by_role('button',name='Сохранить шаблон',exact=True).click();page.wait_for_url('**/employer/team-needs?saved=*')
    page.goto(matching_server+'/employer/search');page.locator('[data-need-select]').select_option(label='Команда нового проекта')
    page.wait_for_url('**/employer/search?need_id=*')
    expect(page.locator('.team-search-group')).to_have_count(2)
    expect(page.locator('.team-search-group').nth(1)).to_contain_text('Frontend Junior')
    saved_url=page.url
    page.locator('.team-search-group').first.get_by_role('link',name='Посмотреть профиль').first.click()
    page.get_by_role('link',name='Поиск кандидатов',exact=True).last.click()
    assert page.url==saved_url
    page.reload();expect(page.locator('[data-need-select]')).to_have_value(parse_qs(urlsplit(saved_url).query)['need_id'][0])
    for width in [1440,390]:
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        expect(page.locator('.sidebar a[aria-current=page]')).to_contain_text('Поиск кандидатов')
    page.goto(matching_server+'/employer/team-needs')
    expect(page.locator('.sidebar a[aria-current=page]')).to_contain_text('Потребность команды')
    context.close()
