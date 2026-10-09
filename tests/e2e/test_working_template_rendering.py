"""Browser-only rendering fixtures. No production route, DB, service overrides or writes.
These check presentation and contracts, not persistence or authenticated backend flows.
"""
import os
from datetime import datetime, UTC
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import urlsplit
import pytest
from fastapi import Request
from playwright.sync_api import expect
from app.main import app
from app.web.templates import templates

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="Set RUN_E2E=1")]
SCREENSHOTS = Path(os.getenv("E2E_SCREENSHOTS", str(Path(__file__).resolve().parents[2] / "docs/design-preview/screenshots")))

def fixture_request(path, base_url):
    parsed=urlsplit(base_url)
    return Request(dict(type="http",http_version="1.1",method="GET",scheme=parsed.scheme,server=(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80)),path=path,root_path="",query_string=b"",headers=[(b"host",parsed.netloc.encode("ascii"))],app=app,router=app.router))

def scenarios():
    now = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
    candidate = NS(email="fixture@example.test", role=NS(value="candidate"))
    employer = NS(email="company-fixture@example.test", role=NS(value="employer"))
    spec, grade = NS(name="Backend-разработка", code="backend", id=1), NS(name="Middle", code="middle", id=1)
    profile = NS(full_name="Тестовый кандидат", phone="", location="Москва", about="Тестовая запись для проверки вёрстки, без сохранения в БД.", desired_role="Backend", desired_salary_from=180000, desired_salary_to=240000, work_format=NS(value="remote"), experience_years=4, skills=[NS(id=1, skill="Python", level="Middle"),NS(id=2,skill="PostgreSQL",level=None)], experiences=[NS(id=1,company_name="Тестовая компания",position="Backend-разработчик",started_at="2023-01-01",ended_at=None,is_current=True,description="Тестовая запись опыта.")])
    category = dict(status="confirmed",confirmed_at=now,specialization=spec,grade=grade)
    cooldown = dict(active=False,days_left=0,next_allowed_at=None)
    attempt = NS(id=7,passed=True,status="completed",started_at=now,score=87)
    state = dict(score=87,questions=[dict(question=dict(text="Тестовый вопрос: какой метод получает ресурс?"),given=dict(value="GET"),is_correct=True),dict(question=dict(text="Тестовый вопрос: что означает 404?"),given=None,is_correct=False)])
    yield "candidate-profile", "candidates/profile.html", "/candidate/profile", dict(user=candidate, profile=profile, work_formats=[NS(value=x) for x in ("office","remote","hybrid")],error=None)
    yield "candidate-error", "candidates/profile.html", "/candidate/profile", dict(user=candidate,profile=profile,work_formats=[NS(value="remote")],error="Зарплата «от» не может быть больше «до»")
    yield "employer-profile", "employers/profile.html", "/employer/profile", dict(user=employer,error=None,profile=NS(company_name="Тестовая компания",description="Тестовый профиль для проверки интерфейса.",industry="IT",website="https://example.test",contact_email="team@example.test",contact_phone=""))
    yield "assessment-history", "assessments/index.html", "/assessments", dict(user=candidate,current=category,cooldown=cooldown,active_attempt_id=8,attempts=[dict(id=7,status="completed",score=87,passed=True,started_at=now,specialization=spec,grade=grade),dict(id=8,status="in_progress",score=None,passed=None,started_at=now,specialization=spec,grade=grade)])
    yield "assessment-empty", "assessments/index.html", "/assessments", dict(user=candidate,current=None,cooldown=cooldown,active_attempt_id=None,attempts=[])
    yield "assessment-start", "assessments/start.html", "/assessments/start", dict(user=candidate,specializations=[spec],grades=[grade],error=None)
    yield "assessment-blocked", "assessments/start.html", "/assessments/start", dict(user=candidate,specializations=[spec],grades=[grade],error="Смена грейда временно недоступна. Тестовое сообщение сервера.")
    yield "assessment-question", "assessments/attempt.html", "/assessments/attempt/7", dict(user=candidate,attempt=attempt,spec=spec,grade=grade,answered_count=3,total=10,current=dict(answer_id=17,text="Какой HTTP-метод используется для получения ресурса?",options=["POST","GET","DELETE","PATCH"]))
    yield "assessment-finish", "assessments/finish.html", "/assessments/attempt/7/finish", dict(user=candidate,attempt_id=7)
    yield "assessment-result", "assessments/result.html", "/assessments/attempt/7/result", dict(user=candidate,attempt=attempt,spec=spec,grade=grade,state=state,current=category,cooldown=cooldown)
    yield "auth-login-error", "auth/login.html", "/auth/login", dict(user=None,email="fixture@example.test",next="/candidate/profile",error="Неверный email или пароль")
    yield "auth-register-error", "auth/register.html", "/auth/register", dict(user=None,email="fixture@example.test",role="candidate",full_name="Тестовый кандидат",error="Пользователь с таким email уже зарегистрирован")
    yield "auth-verified", "auth/verify_result.html", "/auth/verify", dict(user=None,success=True,message="Email подтверждён. Теперь можно войти.")
    yield "auth-verify-error", "auth/verify_result.html", "/auth/verify", dict(user=None,success=False,message="Ссылка недействительна или истекла. Запросите письмо заново.")

@pytest.mark.parametrize("width", [1440,390,320])
def test_working_templates_with_browser_fixtures(page, app_base_url, width):
    page.set_viewport_size({"width":width,"height":1000})
    errors=[]; writes=[]
    page.on("pageerror",lambda error: errors.append(str(error)))
    def prevent_writes(route):
        if route.request.method != "GET":
            writes.append(route.request.url); route.abort()
        else: route.continue_()
    page.route("**/*",prevent_writes)
    for name,template,path,context in scenarios():
        request=fixture_request(path, app_base_url)
        html=templates.TemplateResponse(request=request,name=template,context=context).body.decode("utf-8")
        html=html.replace("</header>","</header><div class='demo-banner'>Тестовый рендер рабочего шаблона · фикстуры · без БД</div>",1)
        url=app_base_url+"/design-preview/__test-render/"+name
        page.route(url,lambda route: route.fulfill(status=200,content_type="text/html; charset=utf-8",body=html))
        page.goto(url);page.evaluate("document.fonts.ready")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"),name
        if "error" in name or "blocked" in name:
            expect(page.locator(".alert-error")).to_be_visible()
        if name=="assessment-question":
            page.get_by_label("GET",exact=True).check()
            assert page.locator("input[name='answer_id']").input_value()=="17"
            assert page.locator("form[action='/assessments/attempt/7/answer']").get_attribute("method")=="post"
        if width!=320:
            SCREENSHOTS.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(SCREENSHOTS/f"working-{name}-{width}.png"),full_page=True)
        page.unroute(url)
    assert errors==[]
    assert writes==[]


def test_original_post_payloads_intercepted_before_network(page, app_base_url):
    # Interception deliberately stops every POST from reaching the application.
    captured=[]
    def block_post(route):
        if route.request.method == "POST":
            from urllib.parse import parse_qs
            captured.append((route.request.url, parse_qs(route.request.post_data or "")))
            route.fulfill(status=200,content_type="text/html",body="<p>Test-only POST interception. No database write.</p>")
        else: route.continue_()
    page.route("**/*",block_post)
    expected={"candidate-profile":("/candidate/profile","full_name","Тестовый кандидат"),"employer-profile":("/employer/profile","company_name","Тестовая компания"),"assessment-question":("/assessments/attempt/7/answer","answer_id","17"),"assessment-finish":("/assessments/attempt/7/finish",None,None),"assessment-start":("/assessments/start","specialization","backend")}
    for name,template,path,context in scenarios():
        if name not in expected: continue
        request=fixture_request(path, app_base_url)
        html=templates.TemplateResponse(request=request,name=template,context=context).body.decode("utf-8")
        url=app_base_url+"/design-preview/__test-render/"+name
        page.route(url,lambda route: route.fulfill(status=200,content_type="text/html; charset=utf-8",body=html))
        page.goto(url)
        if name=="assessment-question":page.get_by_label("GET",exact=True).check()
        action,field,value=expected[name]
        form=page.locator(f"form[action='{action}']")
        with page.expect_response(lambda response: response.request.method=="POST"):
            form.locator("button[type='submit']").click()
        assert captured[-1][0]==app_base_url+action
        if field:assert captured[-1][1][field]==[value]
        if name=="assessment-question":assert captured[-1][1]["value"]==["GET"]
        page.unroute(url)
    assert len(captured)==5
