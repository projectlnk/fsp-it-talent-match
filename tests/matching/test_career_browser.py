"""Three short Chromium paths; fixtures own PostgreSQL databases, Mailpit/mock are local."""
import os
import re
import uuid
from urllib.parse import urlparse
import httpx
import pytest
from playwright.sync_api import expect
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.modules.auth.security import create_access_token, hash_password
from app.modules.auth.models import User
from app.modules.assessments.models import TestAnswer, TestAttempt
from app.modules.assessments.seed_loader import load_questions_from_file, SEED_DIR
from app.modules.candidates.models import CandidateProfile, FspAchievement
from app.modules.career.models import Opportunity, Application, Meeting, DemoSet
from app.modules.career import service as s
from tests.matching.test_career_workflows import career, job

@pytest.fixture
def local_services(monkeypatch):
    settings=get_settings()
    monkeypatch.setattr(settings,'smtp_host','localhost')
    monkeypatch.setattr(settings,'smtp_port',int(os.getenv('CAREER_MAIL_SMTP','65240')))
    monkeypatch.setattr(settings,'fsp_base_url',os.environ['CAREER_MOCK_URL'])
    monkeypatch.setattr(settings,'bcrypt_rounds',4)
    return os.getenv('CAREER_MAIL_URL','http://localhost:65241')

def login_cookie(context, base, uid):
    context.add_cookies([{'name':'access_token','value':create_access_token(uid),'url':base,'httpOnly':True,'sameSite':'Lax'}])

def test_browser_main_two_roles(browser,career,matching_server,local_services,monkeypatch):
    db,e,c,company=career;engine=db.bind;base=matching_server
    monkeypatch.setattr(get_settings(),'app_base_url',base)
    load_questions_from_file(db,SEED_DIR/'backend_middle.json')
    email=f'career-browser-{uuid.uuid4().hex[:10]}@example.com'
    candidate_context=browser.new_context();employer_context=browser.new_context()
    try:
        p=candidate_context.new_page();p.goto(base+'/auth/register')
        p.locator('[name=email]').fill(email);p.locator('[name=password]').fill('test1234')
        p.locator('[name=full_name]').fill('Анна Проверочная');p.locator('[name=processing_consent]').check()
        p.get_by_role('button',name='Зарегистрироваться').click()
        expect(p.locator('main')).to_contain_text('По умолчанию ваш профиль скрыт')
        messages=httpx.get(local_services+'/api/v1/messages').json()['messages']
        msg=next(m for m in messages if any(recipient['Address']==email for recipient in m['To']))
        content=httpx.get(local_services+'/api/v1/message/'+msg['ID']).json()
        link=re.search(r'https?://[^\s<]+/auth/verify\?token=[A-Za-z0-9_\-]+',content['Text']).group(0)
        assert link.startswith(base+'/auth/verify?') and 'http://app:' not in link
        p.goto(link);expect(p.locator('main')).to_contain_text('подтвержд')
        p.goto(base+'/auth/login');p.locator('[name=email]').fill(email);p.locator('[name=password]').fill('test1234');p.locator('form[action="/auth/login"] button').click()
        p.goto(base+'/candidate/profile');p.locator('[name=phone]').fill('+7 000 111-22-33');p.locator('[name=work_format]').select_option('remote');p.get_by_role('button',name='Сохранить профиль').click()
        p.goto(base+'/assessments/start');p.locator('[name=specialization]').select_option('backend');p.locator('[name=grade]').select_option('middle');p.get_by_role('button',name='Начать',exact=True).click()
        aid=int(re.search(r'/attempt/(\d+)',p.url).group(1))
        for index in range(10):
            answer_id=int(p.locator('[name=answer_id]').input_value())
            with Session(engine) as check: snap=check.get(TestAnswer,answer_id).question_snapshot
            chosen=snap['correct'] if index<9 else next(v for v in snap['options'] if v!=snap['correct'])
            p.locator('input[name=value]').filter().evaluate_all('(els, value) => els.find(el => el.value === value).click()',chosen)
            p.get_by_role('button',name='Ответить и продолжить').click()
        p.get_by_role('button',name='Завершить и посмотреть результат').click();expect(p.locator('main')).to_contain_text('90%')
        p.goto(base+'/candidate/profile');p.locator('[name=published]').check();expect(p.locator('[data-visibility-status]')).to_contain_text('Сохранено')
        with Session(engine) as check:
            person=check.scalar(select(User).where(User.email==email));profile=check.scalar(select(CandidateProfile).where(CandidateProfile.user_id==person.id));cid=profile.id
            assert profile.is_searchable and person.is_email_verified
        login_cookie(employer_context,base,e.id);q=employer_context.new_page();q.goto(base+'/career/opportunities/new?kind=need')
        q.locator('[name=title]').fill('Потребность API');q.locator('[name=description]').fill('Разработка API и транзакций PostgreSQL');q.locator('[name=specialization]').select_option('backend');q.locator('[name=grade]').select_option('middle');q.locator('[name=work_format]').select_option('remote');q.locator('[name=skills]').fill('Python, SQL');q.locator('[name=contact_method]').fill('Внутреннее общение');q.get_by_role('button',name='Сохранить',exact=True).click()
        q.reload();expect(q.locator('main')).to_contain_text('Анна Проверочная')
        q.goto(base+f'/employer/candidates/{cid}');q.locator('[name=title]').fill('Приглашение API');q.locator('[name=description]').fill('Разработка API нашей команды');q.locator('[name=salary_from]').fill('100000');q.locator('[name=salary_to]').fill('150000');q.locator('[name=contact_method]').fill('Внутреннее общение');q.get_by_role('button',name='Пригласить',exact=True).click()
        p.goto(base+'/candidate/offers');p.get_by_role('link',name='Приглашение API',exact=True).click();p.locator('form:has(input[value="accepted"]) button').click()
        q.goto(base+f'/career/threads/{company.id}/{cid}');expect(q.locator('main')).to_contain_text(email)
        q.locator('[name=body]').fill('Согласуем встречу');q.get_by_role('button',name='Отправить',exact=True).click();expect(q.locator('main')).to_contain_text('Согласуем встречу')
    finally:candidate_context.close();employer_context.close()

def test_browser_vacancy_application_activity(browser,career,matching_server,local_services):
    db,e,c,company=career;row=job(db,e);db.commit();base=matching_server
    candidate_context=browser.new_context();employer_context=browser.new_context()
    try:
        login_cookie(candidate_context,base,c.id);login_cookie(employer_context,base,e.id)
        p=candidate_context.new_page();q=employer_context.new_page();p.goto(base+f'/career/opportunities/{row.id}')
        p.locator('[name=message]').fill('Интересна работа с API');p.locator('[name=share_contacts]').check();p.get_by_role('button',name='Отправить отклик').click();expect(p.locator('main')).to_contain_text('submitted')
        q.goto(base+'/career/applications');q.locator('form:has(input[value="accepted"]) button').click();expect(q.locator('main')).to_contain_text('accepted')
        q.goto(base+'/career/leaderboard');expect(q.locator('main')).to_contain_text('7');expect(q.locator('main')).to_contain_text('Первое содержательное решение')
        q.reload();expect(q.locator('main')).to_contain_text('7')
    finally:candidate_context.close();employer_context.close()

def test_browser_demo_time_registry_import(browser,career,matching_server,local_services,monkeypatch):
    db,e,c,company=career;settings=get_settings();base=matching_server
    from pydantic import SecretStr
    monkeypatch.setattr(settings,'demo_mode',True);monkeypatch.setattr(settings,'demo_operator_ids',str(e.id));monkeypatch.setattr(settings,'demo_mock_key',SecretStr('isolated-mock-check-only'))
    operator_context=browser.new_context();candidate_context=browser.new_context()
    try:
        login_cookie(operator_context,base,e.id);p=operator_context.new_page();p.goto(base+'/design-preview')
        p.locator('[name=password]').fill('demo12345');p.get_by_role('button',name='Создать набор',exact=True).click();expect(p.locator('main')).to_contain_text('scenario-')
        p.locator('button[name=days][value="2"]').click();expect(p.locator('main')).to_contain_text('scheduled → confirmed');expect(p.locator('main')).to_contain_text('stable → inactive')
        pid='browser-'+uuid.uuid4().hex[:10]
        details=p.locator('details').filter(has=p.get_by_text('Создать / изменить участника',exact=True));details.locator('summary').click()
        f=details.locator('form');f.locator('[name=id]').fill(pid);f.locator('[name=display_name]').fill('Демо участник браузера');f.locator('[name=email]').fill('demo-participant@example.com');f.get_by_role('button').click()
        details=p.locator('details').filter(has=p.get_by_text('Добавить / изменить участие или достижение',exact=True));details.locator('summary').click();f=details.locator('form');f.locator('[name=id]').fill(pid+'-award');f.locator('[name=participant_id]').fill(pid);f.locator('[name=title]').fill('Проверенное достижение mock');f.locator('[name=competition_name]').fill('Тестовый турнир');f.locator('[name=discipline_code]').fill('backend');f.locator('[name=competition_date]').fill('2026-10-01');f.locator('[name=place]').fill('1');f.get_by_role('button').click()
        login_cookie(candidate_context,base,c.id);q=candidate_context.new_page();q.goto(base+'/candidate/profile');q.locator('[name=participant_id]').fill(pid);q.get_by_role('button',name='Привязать',exact=True).click();expect(q.locator('main')).to_contain_text('Проверенное достижение mock')
        q.get_by_role('button',name='Обновить достижения').click();expect(q.locator('main')).to_contain_text('Проверенное достижение mock')
        with Session(db.bind) as check:
            assert check.scalar(select(func.count(FspAchievement.id)).where(FspAchievement.external_achievement_id==pid+'-award'))==1
    finally:operator_context.close();candidate_context.close()
