"""One local browser flow against the guarded disposable Compose stack."""
import os
import uuid
import httpx
import pytest
from playwright.sync_api import expect
from sqlalchemy import delete
from app.db.session import SessionLocal
from app.modules.auth.models import User

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1', reason='Requires isolated local Compose')]

def test_candidate_registration_profile_and_visibility(page):
    base = os.environ['APP_BASE_URL']
    email = 'ui-calibration-' + uuid.uuid4().hex + '@example.com'
    try:
        page.goto(base + '/auth/register')
        page.locator('[name=email]').fill(email)
        page.locator('[name=password]').fill('local-test1234')
        page.locator('[name=full_name]').fill('Проверка интерфейса')
        page.locator('[name=role]').select_option('candidate')
        page.locator('button[type=submit]').click()
        expect(page.get_by_text('По умолчанию ваш профиль скрыт', exact=False)).to_be_visible()
        mail = httpx.get(os.environ['MAILPIT_BASE_URL'] + '/api/v1/messages').json()
        assert any(any(a.get('Address') == email for a in m.get('To', [])) for m in mail['messages'])
        page.goto(base + '/auth/login')
        page.locator('[name=email]').fill(email)
        page.locator('[name=password]').fill('local-test1234')
        page.locator('button[type=submit]').click()
        page.goto(base + '/candidate/profile')
        expect(page.locator('[data-profile-visibility-indicator]')).to_contain_text('Профиль скрыт от работодателей')
        assert page.locator('[name=grade] option').evaluate_all('(options) => options.map(o => o.value)') == ['intern','junior','middle','senior']
        page.locator('[name=grade]').select_option('junior')
        page.locator('[name=about]').fill('Локальная проверка сохранения')
        page.locator('form[action="/candidate/profile"] button[type=submit]').click()
        expect(page.locator('[name=about]')).to_have_value('Локальная проверка сохранения')
        page.locator('[name=published]').check()
        expect(page.locator('[data-visibility-status]')).to_have_text('Сохранено')
        expect(page.locator('[data-profile-visibility-indicator]')).to_contain_text('Профиль доступен работодателям при подтверждённой категории')
        page.locator('[name=published]').uncheck()
        expect(page.locator('[data-visibility-status]')).to_have_text('Сохранено')
        expect(page.locator('[data-profile-visibility-indicator]')).to_contain_text('Профиль скрыт от работодателей')
        for width in [1440, 390]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('form[action="/auth/logout"] button').click()
        expect(page.locator('.account-email')).to_have_count(0)
    finally:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.email == email))
            session.commit()
