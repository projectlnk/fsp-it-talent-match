"""E2E-тесты потока аутентификации через браузер."""
from __future__ import annotations

import os
import uuid

import pytest
from playwright.sync_api import expect

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("RUN_E2E") != "1",
        reason="Set RUN_E2E=1 and install Chromium",
    ),
]


def _email() -> str:
    return f"auth-e2e-{uuid.uuid4().hex[:12]}@example.com"


def _register_via_form(page, base: str, email: str) -> None:
    page.goto(f"{base}/auth/register")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', "test1234")
    page.select_option('select[name="role"]', "candidate")
    page.fill('input[name="full_name"]', "E2E Test")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{base}/auth/check-email")


def _login_via_form(page, base: str, email: str) -> None:
    page.goto(f"{base}/auth/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', "test1234")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{base}/")


def test_register_redirects_to_check_email(page, app_base_url):
    base = app_base_url.rstrip("/")
    email = _email()
    _register_via_form(page, base, email)
    expect(page.get_by_role("heading", name="Проверьте почту")).to_be_visible()


def test_login_shows_email_in_header(page, app_base_url):
    base = app_base_url.rstrip("/")
    email = _email()
    _register_via_form(page, base, email)
    _login_via_form(page, base, email)
    expect(page.locator(".topnav")).to_contain_text(email)
    expect(page.get_by_role("button", name="Выйти")).to_be_visible()


def test_logout_returns_to_guest_state(page, app_base_url):
    base = app_base_url.rstrip("/")
    email = _email()
    _register_via_form(page, base, email)
    _login_via_form(page, base, email)

    page.get_by_role("button", name="Выйти").click()
    page.wait_for_url(f"{base}/")
    expect(page.get_by_role("link", name="Войти")).to_be_visible()
    expect(page.get_by_role("link", name="Регистрация")).to_be_visible()


def test_register_duplicate_shows_error(page, app_base_url):
    base = app_base_url.rstrip("/")
    email = _email()
    _register_via_form(page, base, email)

    page.goto(f"{base}/auth/register")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', "other1234")
    page.select_option('select[name="role"]', "candidate")
    page.click('button[type="submit"]')
    expect(page.locator(".alert-error")).to_contain_text("уже зарегистрирован")


def test_wrong_password_shows_error(page, app_base_url):
    base = app_base_url.rstrip("/")
    email = _email()
    _register_via_form(page, base, email)

    page.goto(f"{base}/auth/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', "wrong1234")
    page.click('button[type="submit"]')
    expect(page.locator(".alert-error")).to_contain_text("Неверный")