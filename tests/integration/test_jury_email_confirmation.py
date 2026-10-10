"""Single browser confirmation flow against the isolated Compose stack."""
import os
import time
import uuid
from urllib.parse import urlsplit

import httpx
import pytest
from playwright.sync_api import expect
from sqlalchemy import delete, select
from app.db.session import SessionLocal
from app.modules.auth.models import User

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1', reason='Requires isolated Compose')]


def test_register_mailpit_confirm_login(page):
    base = os.environ['APP_BASE_URL'].rstrip('/')
    mailpit = os.environ['MAILPIT_BASE_URL'].rstrip('/')
    address = 'jury-confirm-' + uuid.uuid4().hex + '@example.com'
    for _ in range(30):
        try:
            if httpx.get(base + '/readiness', timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    else:
        pytest.fail('Isolated application did not become ready')
    try:
        page.goto(base + '/auth/register')
        page.locator('[name=email]').fill(address)
        page.locator('[name=password]').fill('jury-test1234')
        page.locator('[name=full_name]').fill('Проверка жюри')
        page.locator('[name=role]').select_option('candidate')
        page.locator('button[type=submit]').click()
        expect(page).to_have_url(base + '/auth/check-email?registered=candidate')
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == address))
            assert user is not None and user.is_email_verified is False

        message = None
        for _ in range(20):
            messages = httpx.get(mailpit + '/api/v1/messages', timeout=5).json()['messages']
            message = next((m for m in messages if any(a.get('Address') == address for a in m.get('To', []))), None)
            if message:
                break
            time.sleep(.1)
        assert message is not None, 'Registration email not received by isolated Mailpit'
        page.goto(mailpit + '/view/' + message['ID'])
        link = page.frame_locator('iframe').get_by_role('link', name='Подтвердить email', exact=True)
        expect(link).to_be_visible()
        parsed = urlsplit(link.get_attribute('href'))
        expected = urlsplit(base)
        assert (parsed.scheme, parsed.netloc, parsed.path) == (expected.scheme, expected.netloc, '/auth/verify')
        # Click the actual link in Mailpit; never replace the hostname or token.
        with page.expect_popup() as popup:
            link.click()
        confirmation = popup.value
        expect(confirmation.get_by_text('Email подтверждён. Теперь можно войти.', exact=True)).to_be_visible()
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == address))
            assert user.is_email_verified is True
        confirmation.goto(base + '/auth/login')
        confirmation.locator('[name=email]').fill(address)
        confirmation.locator('[name=password]').fill('jury-test1234')
        confirmation.locator('button[type=submit]').click()
        expect(confirmation.locator('.account-email')).to_have_text(address)
    finally:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.email == address))
            session.commit()
