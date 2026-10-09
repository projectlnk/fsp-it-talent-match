import os
import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="Set RUN_E2E=1 and install Chromium")]

def test_page_and_local_assets(page, app_base_url):
    errors = []
    responses = {}
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("response", lambda response: responses.update({response.url: response.status}))
    base = app_base_url.rstrip("/")
    page.goto(base)
    expect(page.get_by_role("heading", name="Талант виден в деле.")).to_be_visible()
    expect(page.locator("#js-status")).to_have_text("JavaScript работает")
    assert page.evaluate("typeof htmx") == "object"
    assert page.locator("body").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(250, 250, 250)"
    page.locator(".diagnostics summary").click()
    page.get_by_role("button", name="Проверить приложение").click()
    expect(page.locator("#health-result")).to_contain_text('"status":"ok"')
    for asset in ("css/main.css", "js/main.js", "vendor/htmx.min.js"):
        assert responses[base + "/static/" + asset] == 200
    assert errors == []


def test_swagger(page, app_base_url):
    page.goto(app_base_url.rstrip("/") + "/docs")
    expect(page.locator(".swagger-ui .info .title")).to_contain_text("Project API")
    expect(page.locator(".swagger-ui .opblock-summary-path", has_text="/health")).to_be_visible()
    expect(page.locator(".swagger-ui .opblock-summary-path", has_text="/readiness")).to_be_visible()
