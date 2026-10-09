"""UI checks for the isolated prototype. No real registration or DB writes."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="Set RUN_E2E=1")]
SCREENSHOTS = Path(os.getenv("E2E_SCREENSHOTS", str(Path(__file__).resolve().parents[2] / "docs" / "design-preview" / "screenshots")))
PATHS = ["/", "/auth/login", "/auth/register", "/auth/check-email", "/design-preview", "/design-preview/candidate", "/design-preview/employer", "/design-preview/search", "/design-preview/person/1", "/design-preview/person/2", "/design-preview/invitation", "/design-preview/fsp", "/design-preview/privacy", "/design-preview/resume"]

@pytest.mark.parametrize("width", [1440, 390, 320])
def test_screens_navigation_no_errors_or_overflow(page, app_base_url, width):
    page.set_viewport_size({"width": width, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    for path in PATHS:
        response = page.goto(app_base_url + path)
        assert response.status == 200, path
        page.evaluate("document.fonts.ready")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), path
        if path.startswith("/design-preview"):
            expect(page.locator(".demo-banner")).to_be_visible()
        if width != 320:
            name = path.strip("/").replace("/", "-") or "home"
            page.screenshot(path=str(SCREENSHOTS / f"{name}-{width}.png"), full_page=True)
    page.goto(app_base_url + "/design-preview")
    page.locator(".screen-index a[href='/design-preview/search']").click()
    expect(page).to_have_url(app_base_url + "/design-preview/search")
    assert errors == []

def test_filter_empty_state_and_candidate_navigation(page, app_base_url):
    page.goto(app_base_url + "/design-preview/search")
    page.locator("select[name='specialization']").select_option("backend")
    page.get_by_role("button", name="Применить", exact=True).click()
    expect(page.locator("[data-candidate-card]:visible")).to_have_count(2)
    page.locator("input[name='query']").fill("несуществующий")
    page.get_by_role("button", name="Применить", exact=True).click()
    expect(page.locator("#search-empty")).to_be_visible()
    page.get_by_role("button", name="Сбросить фильтры", exact=True).click()
    expect(page.locator("[data-candidate-card]:visible")).to_have_count(3)
    page.get_by_role("link", name="Анна Соколова", exact=True).click()
    expect(page.locator("main")).to_contain_text("Истории ФСП нет")
    expect(page.locator("[data-contact-open]")).to_be_hidden()
    page.get_by_role("link", name="Пригласить в команду →").click()
    expect(page).to_have_url(app_base_url + "/design-preview/invitation?candidate=2")

def test_invitation_accept_decline_contacts_and_consent(page, app_base_url):
    page.goto(app_base_url + "/design-preview/invitation")
    expect(page.locator("#invite-contact")).to_be_hidden()
    page.get_by_role("button", name="Отказаться", exact=True).click()
    expect(page.locator("#invite-status")).to_have_text("Отказ")
    expect(page.locator("#invite-contact")).to_be_hidden()
    page.get_by_role("button", name="Сбросить демо").click()
    page.get_by_role("button", name="Принять приглашение", exact=True).click()
    expect(page.locator("#invite-status")).to_have_text("Принято")
    expect(page.locator("#invite-contact")).to_be_visible()
    expect(page.get_by_role("button", name="Отказаться", exact=True)).to_be_disabled()
    page.goto(app_base_url + "/design-preview/person/1")
    expect(page.locator("[data-contact-open]")).to_be_visible()
    page.goto(app_base_url + "/design-preview/privacy")
    page.locator("input[name='contacts']").uncheck()
    page.get_by_role("button", name="Сохранить демо-настройки").click()
    page.goto(app_base_url + "/design-preview/person/1")
    expect(page.locator("[data-contact-open]")).to_be_hidden()
    page.goto(app_base_url + "/design-preview/privacy")
    expect(page.locator("input[name='contacts']")).not_to_be_checked()

def test_demo_forms_salary_fsp_and_print(page, app_base_url):
    page.goto(app_base_url + "/design-preview/invitation")
    page.locator("input[name='salary_from']").fill("300000")
    page.get_by_role("button", name="Показать демо-отправку →").click()
    expect(page.locator("[data-demo-error]")).to_be_visible()
    page.locator("input[name='salary_from']").fill("180000")
    page.get_by_role("button", name="Показать демо-отправку →").click()
    expect(page.locator("#toast")).to_contain_text("не отправлено")
    page.goto(app_base_url + "/design-preview/fsp")
    expect(page.locator("[data-fsp-import]")).to_be_disabled()
    page.locator("[data-fsp-link]").click()
    page.locator("[data-fsp-import]").click()
    page.locator("[data-fsp-import]").click()
    expect(page.locator("#fsp-achievements")).to_be_visible()
    expect(page.locator("#fsp-achievements h3")).to_have_count(1)
    page.goto(app_base_url + "/design-preview/resume")
    page.evaluate("window.print = () => { window.printWasCalled = true; }")
    page.locator("[data-print-resume]").click()
    assert page.evaluate("window.printWasCalled") is True
    page.emulate_media(media="print")
    expect(page.locator(".resume-sheet")).to_be_visible()
    expect(page.locator(".demo-banner")).to_be_hidden()

def test_real_auth_native_validation_without_submission(page, app_base_url):
    page.goto(app_base_url + "/auth/register")
    form = page.locator("form[action='/auth/register']")
    assert form.get_attribute("method") == "post"
    assert page.locator("input[name='password']").get_attribute("minlength") == "8"
    assert page.evaluate("document.querySelector('form[action=\"/auth/register\"]').checkValidity()") is False
    page.locator("input[name='email']").fill("candidate@example.com")
    page.locator("input[name='password']").fill("test1234")
    page.locator("select[name='role']").select_option("employer")
    assert page.evaluate("document.querySelector('form[action=\"/auth/register\"]').checkValidity()") is True
    page.goto(app_base_url + "/auth/login?next=/candidate/profile")
    assert page.locator("input[name='next']").input_value() == "/candidate/profile"
