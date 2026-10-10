"""Small real two-tab tests; no full E2E suite or external services."""
import pytest
from playwright.sync_api import expect
from sqlalchemy.orm import Session
from app.modules.auth.models import User
from app.modules.auth.security import hash_password

@pytest.mark.parametrize('fallback', [False, True])
def test_two_tab_auth(browser, matching_server, database, fallback):
    with Session(database[0]) as session:
        user = session.get(User, database[1]['candidate'].id)
        user.password_hash = hash_password('test1234')
        session.commit()
    context = browser.new_context()
    if fallback:
        context.add_init_script('window.BroadcastChannel = undefined')
    first = context.new_page()
    second = context.new_page()
    try:
        first.goto(matching_server + '/auth/login')
        second.goto(matching_server + '/auth/login')
        first.locator('[name=email]').fill(database[1]['candidate'].email)
        first.locator('[name=password]').fill('test1234')
        first.locator('button[type=submit]').click()
        expect(second.locator('.account-email')).to_have_text(database[1]['candidate'].email)
        second.goto(matching_server + '/candidate/profile')
        second.locator('[name=about]').fill('Unsaved draft')
        first.locator('form[action="/auth/logout"] button').click()
        expect(second.locator('#auth-sync-notice')).to_be_visible()
        expect(second.locator('[name=about]')).to_have_value('Unsaved draft')
        second.once('dialog', lambda dialog: dialog.dismiss())
        second.locator('#auth-sync-notice button').click()
        expect(second.locator('[name=about]')).to_have_value('Unsaved draft')
        second.once('dialog', lambda dialog: dialog.accept())
        second.locator('#auth-sync-notice button').click()
        expect(second.locator('[name=about]')).to_have_count(0)
        # Login again, then clean-tab logout must update automatically.
        first.goto(matching_server + '/auth/login')
        first.locator('[name=email]').fill(database[1]['candidate'].email)
        first.locator('[name=password]').fill('test1234')
        first.locator('button[type=submit]').click()
        second.goto(matching_server + '/')
        expect(second.locator('.account-email')).to_be_visible()
        first.locator('form[action="/auth/logout"] button').click()
        expect(second.locator('.account-email')).to_have_count(0)
    finally:
        context.close()
