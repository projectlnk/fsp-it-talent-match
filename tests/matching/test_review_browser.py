"""Actual profile forms and test continuation on owned PostgreSQL, with browser checks."""
import os
from pathlib import Path
import tempfile
import pytest
from sqlalchemy.orm import Session
from playwright.sync_api import expect
from app.modules.auth.security import create_access_token
from app.modules.assessments.models import Question, QuestionType

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.getenv('RUN_E2E')!='1' or not os.getenv('MATCHING_TEST_DATABASE_URL'),reason='Chromium and owned PostgreSQL required')]

@pytest.mark.parametrize('width',[1440,390])
def test_profile_save_validation_and_resume_test(page,matching_server,database,width):
    engine,data=database
    with Session(engine) as session:
        for index in range(10):
            session.add(Question(specialization_id=data['category'].specialization_id,grade_id=data['category'].grade_id,type=QuestionType.SINGLE_CHOICE,difficulty=1,payload={'text':f'Browser question {index}','options':['Yes','No']},correct_answer={'value':'Yes'}))
        session.commit()
    page.set_extra_http_headers({'Authorization':'Bearer '+create_access_token(data['candidate'].id)})
    page.set_viewport_size({'width':width,'height':1000});errors=[];page.on('pageerror',lambda error: errors.append(str(error)))
    page.goto(matching_server+'/candidate/profile')
    profile_form=page.locator('form[action="/candidate/profile"]')
    profile_form.locator('[name=full_name]').fill('Проверенный профиль')
    profile_form.locator('[name=desired_salary_from]').fill('0')
    profile_form.locator('[name=desired_salary_to]').fill('200000')
    profile_form.locator('button[type=submit]').click();page.wait_for_url(matching_server+'/candidate/profile');page.reload()
    expect(page.locator('[name=full_name]')).to_have_value('Проверенный профиль')
    expect(page.locator('[name=desired_salary_from]')).to_have_value('0')
    profile_form=page.locator('form[action="/candidate/profile"]')
    profile_form.evaluate('(form)=>form.noValidate=true')
    profile_form.locator('[name=experience_years]').fill('81');profile_form.locator('button[type=submit]').click()
    expect(page.locator('.alert-error').first).to_be_visible()
    expect(page.locator('[name=experience_years]')).not_to_have_value('81')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=Path(os.getenv('MATCHING_SCREENSHOTS',tempfile.gettempdir()+'/fsp-review-screenshots'));out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'profile-review-{width}.png'),full_page=True)
    page.goto(matching_server+'/assessments/start')
    page.locator('[name=specialization]').select_option('backend');page.locator('[name=grade]').select_option('middle');page.get_by_role('button',name='Начать',exact=True).click()
    attempt_url=page.url
    page.locator('input[value="Yes"]').check();page.get_by_role('button',name='Ответить и продолжить').click()
    expect(page.locator('.question-meta')).to_contain_text('Вопрос 2 из 10')
    page.goto(matching_server+'/candidate/profile');page.goto(attempt_url)
    expect(page.locator('.question-meta')).to_contain_text('Вопрос 2 из 10')
    for _ in range(9):
        page.locator('input[value="Yes"]').check();page.get_by_role('button',name='Ответить и продолжить').click()
    page.get_by_role('button',name='Завершить и посмотреть результат',exact=True).click()
    expect(page.get_by_role('heading',name='Результат тестирования')).to_be_visible()
    expect(page.locator('.result-score')).to_have_text('100%')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(out/f'assessment-review-{width}.png'),full_page=True)
    assert not errors
