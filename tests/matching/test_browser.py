"""Real web handlers on an isolated database, not intercepted HTML fixtures."""
import os
import tempfile
from pathlib import Path
import pytest
from playwright.sync_api import expect
from app.modules.auth.security import create_access_token
pytestmark=[pytest.mark.e2e,pytest.mark.skipif(os.getenv('RUN_E2E')!='1',reason='Set RUN_E2E=1; Chromium required')]

@pytest.mark.parametrize('width',[1440,390,320])
def test_search_navigation_htmx_mobile(page,matching_server,headers,width):
    page.set_extra_http_headers(headers);page.set_viewport_size({'width':width,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(matching_server+'/employer/search?page_size=2')
    expect(page.locator('#matching-results h2')).to_have_text('Найдено: 4')
    page.get_by_role('link',name='Далее',exact=True).click()
    expect(page).to_have_url(__import__('re').compile('page=2'))
    expect(page.locator('.matching-pagination')).to_contain_text('Страница 2 / 2')
    page.locator('input[name=skills]').fill('Rust');page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.get_by_role('heading',name='Кандидаты не найдены')).to_be_visible()
    assert 'page=2' not in page.url
    page.locator('input[name=skills]').fill('Python, SQL');page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.locator('#matching-results h2')).to_have_text('Найдено: 4')
    page.get_by_role('checkbox',name='Все указанные навыки').check()
    page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.locator('#matching-results h2')).to_have_text('Найдено: 3')
    assert 'all_skills=true' in page.url
    page.get_by_role('link',name='Далее',exact=True).click()
    expect(page.locator('.matching-pagination')).to_contain_text('Страница 2 / 2')
    assert 'all_skills=true' in page.url
    page.reload();expect(page.get_by_role('checkbox',name='Все указанные навыки')).to_be_checked()
    page.get_by_role('checkbox',name='Все указанные навыки').uncheck()
    page.get_by_role('button',name='Найти кандидатов').click()
    expect(page.locator('#matching-results h2')).to_have_text('Найдено: 4')
    assert 'all_skills=' not in page.url
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    out=Path(os.getenv('MATCHING_SCREENSHOTS',tempfile.gettempdir()+'/fsp-matching-screenshots'));out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'search-{width}.png'),full_page=True)
    page.locator('#matching-results a[href="/employer/candidates/1"]').first.click()
    expect(page.get_by_role('heading',name='Подтверждённая категория')).to_be_visible()
    expect(page.get_by_role('button',name='Пригласить',exact=True)).to_be_enabled()
    expect(page.locator('main')).to_contain_text('Истории ФСП нет')
    body=page.content()
    for secret in ['candidate-secret-','secret-contact@example.invalid','secret_handle','999']: assert secret not in body
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(out/f'candidate-{width}.png'),full_page=True)
    assert not errors

def test_publication_roundtrip_in_browser(page,matching_server,database,headers):
    page.set_extra_http_headers({'Authorization':'Bearer '+create_access_token(database[1]['candidate'].id)})
    page.goto(matching_server+'/candidate/search-publication')
    page.get_by_role('checkbox').uncheck();page.get_by_role('button',name='Сохранить публикацию').click()
    expect(page.get_by_role('status')).to_contain_text('Настройка сохранена')
    page.reload();expect(page.get_by_role('checkbox')).not_to_be_checked()
    page.set_extra_http_headers(headers)
    assert page.goto(matching_server+'/employer/candidates/1').status==404

def test_no_js_fallback(browser,matching_server,headers):
    context=browser.new_context(java_script_enabled=False,extra_http_headers=headers)
    page=context.new_page()
    try:
        page.goto(matching_server+'/employer/search')
        page.locator('input[name=skills]').fill('Rust');page.get_by_role('button',name='Найти кандидатов').click()
        expect(page.get_by_role('heading',name='Кандидаты не найдены')).to_be_visible()
    finally: context.close()
