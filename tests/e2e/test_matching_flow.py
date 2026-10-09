"""E2E-тест сквозного сценария подбора: работодатель находит кандидата,
отправляет приглашение, кандидат принимает, контакты раскрываются.

Тест подготавливает данные (подтверждённую категорию кандидата) через
CLI-хелпер внутри контейнера, потому что e2e запускается на хосте и не
имеет прямого доступа к БД.
"""
from __future__ import annotations

import os
import subprocess
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

PREFIX = "match-e2e-"


def _email(role: str) -> str:
    return f"{PREFIX}{role}-{uuid.uuid4().hex[:10]}@example.com"


def _run_in_container(code: str) -> str:
    """Выполняет Python-код внутри контейнера app и возвращает stdout."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "app", "python", "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"container command failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout


@pytest.fixture(autouse=True)
def cleanup():
    """Удаляет тестовых пользователей после каждого теста через контейнер."""
    yield
    code = (
        "from app.db.session import SessionLocal; "
        "from app.modules.auth.models import User; "
        "from sqlalchemy import delete; "
        "s = SessionLocal(); "
        "s.execute(delete(User).where(User.email.like('match-e2e-%'))); "
        "s.commit(); s.close()"
    )
    _run_in_container(code)


def _register_via_form(page, base: str, email: str, password: str, role: str) -> None:
    page.goto(f"{base}/auth/register")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.select_option('select[name="role"]', role)
    page.fill('input[name="full_name"]', "E2E Test")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{base}/auth/check-email")


def _login_via_form(page, base: str, email: str, password: str) -> None:
    page.goto(f"{base}/auth/login")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{base}/")


def _grant_confirmed_category(
    email: str,
    spec_code: str = "backend",
    grade_code: str = "junior",
    phone: str = "+7 999 888-77-66",
) -> None:
    """Через контейнер: подтверждённая категория + телефон в профиле."""
    # 1. Обновляем телефон в профиле
    code = (
        "from app.db.session import SessionLocal; "
        "from app.modules.auth.models import User; "
        "from app.modules.candidates.service import update_profile; "
        "from sqlalchemy import select; "
        "s = SessionLocal(); "
        f"u = s.scalar(select(User).where(User.email == {email!r})); "
        "assert u is not None; "
        f"update_profile(s, user_id=u.id, changes={{'phone': {phone!r}}}); "
        "s.close()"
    )
    _run_in_container(code)

    # 2. Назначаем категорию через CLI-хелпер
    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "app",
            "python", "-m", "app.scripts.grant_category",
            email, spec_code, grade_code,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"grant_category failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def test_full_matching_flow(page, app_base_url):
    """Полный сценарий: работодатель находит, приглашает; кандидат принимает;
    работодатель видит контакты."""
    base = app_base_url.rstrip("/")
    password = "test1234"

    # 1. Готовим кандидата
    cand_email = _email("cand")
    _register_via_form(page, base, cand_email, password, "candidate")
    _grant_confirmed_category(cand_email, "backend", "junior")

    # 2. Готовим работодателя
    emp_email = _email("emp")
    _register_via_form(page, base, emp_email, password, "employer")

    # 3. Входим работодателем и идём в поиск
    _login_via_form(page, base, emp_email, password)
    page.goto(f"{base}/employer/search")
    expect(page.get_by_role("heading", name="Поиск кандидатов")).to_be_visible()

    # Применяем фильтр по специализации и грейду
    page.select_option('select[name="specialization"]', "backend")
    page.select_option('select[name="grade"]', "junior")
    page.get_by_role("button", name="Найти").click()

    # 4. Видим карточку кандидата в списке
    expect(page.locator(".candidate-item").first).to_be_visible()
    expect(page.locator(".candidate-list")).to_contain_text("E2E Test")

    # 5. Открываем карточку
    page.locator(".candidate-link").first.click()
    page.wait_for_url(f"{base}/employer/candidates/*")

    # Контактов в карточке нет
    content = page.content()
    assert "+7 999 888-77-66" not in content
    assert "E2E Test" in content
    expect(page.locator(".alert-info")).to_contain_text("Рейтинг")

    # 6. Отправляем приглашение
    page.fill('input[name="title"]', "Backend Developer E2E")
    page.fill('textarea[name="description"]', "Приходите к нам в команду")
    page.fill('input[name="salary_from"]', "200000")
    page.fill('input[name="salary_to"]', "300000")
    page.fill('input[name="contact_method"]', "Telegram: @hr_e2e")
    page.get_by_role("button", name="Отправить приглашение").click()

    page.wait_for_url(f"{base}/employer/offers")
    expect(page.locator(".table")).to_contain_text("Backend Developer E2E")

    # 7. Открываем детали приглашения
    page.locator("a", has_text="Открыть").first.click()
    page.wait_for_url(f"{base}/employer/offers/*")
    expect(page.locator(".alert")).to_contain_text("Контакты кандидата откроются")

    # 8. Выходим и входим кандидатом
    page.get_by_role("button", name="Выйти").click()
    page.wait_for_url(f"{base}/")

    _login_via_form(page, base, cand_email, password)

    # 9. Кандидат видит входящее приглашение
    page.goto(f"{base}/candidate/offers")
    expect(page.locator(".offer-list")).to_contain_text("Backend Developer E2E")
    expect(page.locator(".offer-item").first).to_contain_text("200000")

    # 10. Открывает приглашение
    page.locator(".offer-item .candidate-link").first.click()
    page.wait_for_url(f"{base}/candidate/offers/*")
    expect(page.get_by_role("heading", name="Backend Developer E2E")).to_be_visible()

    # 11. Принимает
    page.get_by_role("button", name="Принять приглашение").click()
    page.wait_for_load_state("networkidle")
    expect(page.locator(".alert-success")).to_contain_text("Вы приняли приглашение")

    # 12. Выходим, входим работодателем, видим контакты
    page.get_by_role("button", name="Выйти").click()
    page.wait_for_url(f"{base}/")

    _login_via_form(page, base, emp_email, password)
    page.goto(f"{base}/employer/offers")
    page.locator("a", has_text="Открыть").first.click()
    page.wait_for_url(f"{base}/employer/offers/*")

    expect(page.locator(".alert-success")).to_contain_text("Контакты открыты")
    # На странице два блока .kv — берём тот, что в секции контактов
    contacts_section = page.locator(
        ".profile-section", has_text="Контакты кандидата"
    )
    expect(contacts_section).to_contain_text(cand_email)
    expect(contacts_section).to_contain_text("+7 999 888-77-66")


def test_reject_flow_hides_contacts(page, app_base_url):
    """Альтернативный сценарий: кандидат отклоняет — контакты не раскрываются."""
    base = app_base_url.rstrip("/")
    password = "test1234"

    cand_email = _email("cand")
    _register_via_form(page, base, cand_email, password, "candidate")
    _grant_confirmed_category(cand_email, "backend", "junior")

    emp_email = _email("emp")
    _register_via_form(page, base, emp_email, password, "employer")

    # Работодатель отправляет приглашение
    _login_via_form(page, base, emp_email, password)
    page.goto(f"{base}/employer/search?specialization=backend&grade=junior")
    page.locator(".candidate-link").first.click()
    page.wait_for_url(f"{base}/employer/candidates/*")

    page.fill('input[name="title"]', "Reject Test")
    page.fill('input[name="salary_from"]', "100000")
    page.fill('input[name="salary_to"]', "150000")
    page.get_by_role("button", name="Отправить приглашение").click()
    page.wait_for_url(f"{base}/employer/offers")

    # Кандидат отклоняет
    page.get_by_role("button", name="Выйти").click()
    page.wait_for_url(f"{base}/")
    _login_via_form(page, base, cand_email, password)

    page.goto(f"{base}/candidate/offers")
    page.locator(".offer-item .candidate-link").first.click()
    page.wait_for_url(f"{base}/candidate/offers/*")

    page.get_by_role("button", name="Отклонить").click()
    page.wait_for_load_state("networkidle")
    expect(page.locator(".alert-error")).to_contain_text("Вы отклонили приглашение")

    # Работодатель не видит контактов
    page.get_by_role("button", name="Выйти").click()
    page.wait_for_url(f"{base}/")
    _login_via_form(page, base, emp_email, password)

    page.goto(f"{base}/employer/offers")
    page.locator("a", has_text="Открыть").first.click()
    page.wait_for_url(f"{base}/employer/offers/*")

    content = page.content()
    assert "+7 999 888-77-66" not in content
    assert cand_email not in content
    expect(page.locator(".alert-error")).to_contain_text("отклонил")