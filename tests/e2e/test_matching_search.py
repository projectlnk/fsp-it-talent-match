"""Search UI against the real isolated Compose app, including owner publication."""
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
import uuid
import httpx
import pytest
from playwright.sync_api import expect
from sqlalchemy import select, delete
from app.db.session import SessionLocal
from app.core.config import get_settings
from app.modules.auth.models import User
from app.modules.candidates.models import CandidateProfile, CandidateSkill
from app.modules.assessments.models import CandidateCategory, Category, Specialization, Grade, CategoryStatus

pytestmark=[pytest.mark.e2e,pytest.mark.skipif(os.getenv('RUN_E2E')!='1' or not os.getenv('TEST_COMPOSE_PROJECT'),reason='Isolated Docker stack and RUN_E2E=1 required')]

@pytest.fixture
def actors(app_base_url):
    project=os.environ['TEST_COMPOSE_PROJECT']
    assert project.startswith('fsp-matching-check-')
    command=['docker','compose','-f','compose.test.yaml','-p',project]
    app_addr=subprocess.check_output(command+['port','app','8000'],text=True).strip()
    db_addr=subprocess.check_output(command+['port','db','5432'],text=True).strip()
    assert urlsplit(app_base_url).netloc==app_addr
    from sqlalchemy.engine import make_url
    db_url=make_url(get_settings().database_url)
    assert db_url.database=='fsp_matching_test' and f'{db_url.host}:{db_url.port}'==db_addr
    emails={role:'matching-browser-'+role+'-'+uuid.uuid4().hex[:10]+'@example.com' for role in ['candidate','employer']}
    ids=[]
    with httpx.Client(base_url=app_base_url) as client:
        try:
            for role,email in emails.items():
                response=client.post('/api/v1/auth/register',json={'email':email,'password':'test1234','role':role,'full_name':'Docker '+role})
                assert response.status_code==201,response.text
                with SessionLocal() as session:
                    user=session.scalar(select(User).where(User.email==email));ids.append(user.id)
            with SessionLocal() as session:
                user=session.scalar(select(User).where(User.email==emails['candidate']))
                profile=session.scalar(select(CandidateProfile).where(CandidateProfile.user_id==user.id));pid=profile.id
                profile.phone='+7 999 222-11-00'
                profile.about='Работа с API. secret-contact@example.invalid https://t.me/secret_handle'
                sid=session.scalar(select(Specialization.id).where(Specialization.code=='backend'))
                gid=session.scalar(select(Grade.id).where(Grade.code=='junior'))
                cid=session.scalar(select(Category.id).where(Category.specialization_id==sid,Category.grade_id==gid))
                session.add(CandidateCategory(candidate_profile_id=pid,category_id=cid,is_current=True,status=CategoryStatus.CONFIRMED,test_score=85))
                skill='docker-'+uuid.uuid4().hex[:8]
                session.add_all([CandidateSkill(candidate_profile_id=pid,skill=name) for name in [skill,'Python','SQL']]);session.commit()
            yield dict(emails=emails,profile_id=pid,skill=skill)
        finally:
            if ids:
                with SessionLocal() as session:
                    session.execute(delete(User).where(User.id.in_(ids),User.email.like('matching-browser-%')));session.commit()

def login(page,base,email):
    page.goto(base+'/auth/login');page.locator('input[name=email]').fill(email);page.locator('input[name=password]').fill('test1234')
    page.locator('form[action="/auth/login"] button[type=submit]').click();page.wait_for_url(base+'/')

@pytest.mark.parametrize('width',[1440,390,320])
def test_real_docker_search_publication_and_contacts(page,app_base_url,actors,width):
    page.set_viewport_size({'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    base=app_base_url;pid=actors['profile_id']
    login(page,base,actors['emails']['candidate'])
    assert page.goto(base+'/employer/search').status==403
    page.goto(base+'/candidate/search-publication');expect(page.get_by_role('checkbox')).not_to_be_checked()
    page.get_by_role('checkbox').check();page.get_by_role('button',name='Сохранить публикацию').click()
    expect(page.get_by_role('status')).to_contain_text('Настройка сохранена')
    page.get_by_role('button',name='Выйти').click();login(page,base,actors['emails']['employer'])
    page.goto(base+'/employer/search')
    page.select_option('select[name=specialization]','backend');page.select_option('select[name=grade]','junior')
    checkbox=page.get_by_role('checkbox',name='Все указанные навыки')
    expect(checkbox).not_to_be_checked()
    page.locator('input[name=skills]').fill(actors['skill']+', nonexistent-skill')
    page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.locator('#matching-results h2')).to_have_text('Найдено: 1')
    checkbox.check();page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.get_by_role('heading',name='Кандидаты не найдены')).to_be_visible()
    page.locator('input[name=skills]').fill(actors['skill']+', Python')
    page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.locator('#matching-results h2')).to_have_text('Найдено: 1')
    expect(page.locator(f'#matching-results a[href="/employer/candidates/{pid}"]').first).to_be_visible()
    page.locator(f'#matching-results a[href="/employer/candidates/{pid}"]').first.click()
    expect(page.locator('main')).to_contain_text('Истории ФСП нет')
    expect(page.get_by_role('button',name='Пригласить',exact=True)).to_be_disabled()
    content=page.content()
    for secret in [actors['emails']['candidate'],'+7 999 222-11-00','secret-contact@example.invalid','secret_handle']: assert secret not in content
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=Path(os.getenv('DOCKER_SCREENSHOTS',os.environ.get('TEMP','/tmp')+'/fsp-docker-matching'));out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'docker-candidate-{width}.png'),full_page=True)
    page.get_by_role('button',name='Выйти').click();login(page,base,actors['emails']['candidate'])
    page.goto(base+'/candidate/search-publication');page.get_by_role('checkbox').uncheck();page.get_by_role('button',name='Сохранить публикацию').click()
    expect(page.get_by_role('checkbox')).not_to_be_checked()
    page.get_by_role('button',name='Выйти').click();login(page,base,actors['emails']['employer'])
    assert page.goto(base+f'/employer/candidates/{pid}').status==404
    assert not errors
