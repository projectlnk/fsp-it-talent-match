"""Review regressions through real handlers and a fresh owned database."""
from datetime import date
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.modules.auth.web import _safe_next
from app.modules.candidates.models import CandidateProfile, CandidateSkill, CandidateExperience

@pytest.mark.parametrize("value", ["//evil.example", "/\\evil.example", "/\n/evil.example", "https://evil.example"])
def test_next_rejects_browser_external_urls(value):
    assert _safe_next(value) == "/"

def test_next_preserves_local_search():
    assert _safe_next("/employer/search?skills=Python") == "/employer/search?skills=Python"

@pytest.mark.parametrize("field,value", [("full_name", None), ("full_name", "  "), ("experience_years", 81), ("desired_salary_from", -1)])
def test_invalid_profile_patch_leaves_saved_profile(client, candidate_headers, database, field, value):
    before = client.get("/api/v1/candidates/me", headers=candidate_headers).json()
    response = client.patch("/api/v1/candidates/me", headers=candidate_headers, json={field: value})
    assert response.status_code == 422
    assert client.get("/api/v1/candidates/me", headers=candidate_headers).json() == before

def test_salary_partial_patch_checks_stored_other_bound(client, candidate_headers):
    endpoint = "/api/v1/candidates/me"
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_from": 100, "desired_salary_to": 200}).status_code == 200
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_from": 300}).status_code == 400
    assert client.get(endpoint, headers=candidate_headers).json()["desired_salary_from"] == 100
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_to": None}).status_code == 200
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_from": 300}).status_code == 200

@pytest.mark.parametrize("data", [{"experience_years": "81"}, {"desired_salary_from": "-1"}, {"desired_salary_from": "bad"}, {"work_format": "bad"}, {"full_name": " "}])
def test_html_profile_uses_server_validation(client, candidate_headers, data):
    before = client.get("/api/v1/candidates/me", headers=candidate_headers).json()
    response = client.post("/candidate/profile", headers=candidate_headers, data={"full_name": "Valid", **data})
    assert response.status_code == 400 and "text/html" in response.headers["content-type"]
    assert client.get("/api/v1/candidates/me", headers=candidate_headers).json() == before

def test_experience_partial_patch_checks_stored_dates(client, candidate_headers):
    endpoint = "/api/v1/candidates/me/experiences"
    response = client.post(endpoint, headers=candidate_headers, json={"company_name": "Company", "position": "Developer", "started_at": "2024-01-01", "ended_at": "2025-01-01"})
    record = response.json()["experiences"][-1]
    assert client.patch(endpoint + "/" + str(record["id"]), headers=candidate_headers, json={"started_at": "2026-01-01"}).status_code == 400
    after = client.get("/api/v1/candidates/me", headers=candidate_headers).json()["experiences"][-1]
    assert after["started_at"] == "2024-01-01"

@pytest.mark.parametrize("data", [{"started_at": "invalid"}, {"started_at": "2026-01-01", "ended_at": "2025-01-01"}])
def test_html_experience_rejects_invalid_dates(client, candidate_headers, data):
    response = client.post("/candidate/profile/experiences", headers=candidate_headers, data={"company_name": "Company", "position": "Developer", **data})
    assert response.status_code == 400
    assert len(client.get("/api/v1/candidates/me", headers=candidate_headers).json()["experiences"]) == 1

def test_skill_rename_conflict_returns_409_and_rolls_back(client, candidate_headers):
    endpoint = "/api/v1/candidates/me/skills"
    skills = client.get("/api/v1/candidates/me", headers=candidate_headers).json()["skills"]
    sql = next(item for item in skills if item["skill"] == "SQL")
    assert client.patch(endpoint + "/" + str(sql["id"]), headers=candidate_headers, json={"skill": " Python "}).status_code == 409
    assert any(item["skill"] == "SQL" for item in client.get("/api/v1/candidates/me", headers=candidate_headers).json()["skills"])

@pytest.mark.parametrize("skill", [None, "  "])
def test_skill_patch_rejects_empty(client, candidate_headers, skill):
    assert client.patch("/api/v1/candidates/me/skills/1", headers=candidate_headers, json={"skill": skill}).status_code == 422

@pytest.mark.parametrize("email,password,role", [("invalid", "password123", "candidate"), ("user@example.com", "short", "candidate"), ("user@example.com", "password123", "admin")])
def test_html_registration_rejects_before_writing(client, database, email, password, role):
    response = client.post("/auth/register", data={"email": email, "password": password, "role": role})
    assert response.status_code == 400
    from app.modules.auth.models import User
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 10

@pytest.fixture
def employer_profile(database):
    from app.modules.employers.models import EmployerProfile
    with Session(database[0]) as session:
        if database[0].dialect.name == "sqlite": EmployerProfile.__table__.create(database[0])
        profile = EmployerProfile(user_id=database[1]["employer"].id, company_name="Original company")
        session.add(profile); session.commit()

@pytest.mark.parametrize("payload", [{"company_name": None}, {"company_name": "  "}, {"contact_email": "bad"}])
def test_employer_api_rejects_invalid_profile(client, headers, employer_profile, payload):
    assert client.patch("/api/v1/employers/me", headers=headers, json=payload).status_code == 422
    assert client.get("/api/v1/employers/me", headers=headers).json()["company_name"] == "Original company"

def test_employer_html_rejects_invalid_email(client, headers, employer_profile):
    assert client.post("/employer/profile", headers=headers, data={"company_name": "Changed", "contact_email": "bad"}).status_code == 400
    assert client.get("/api/v1/employers/me", headers=headers).json()["company_name"] == "Original company"

def test_invalid_search_filters_have_html_and_htmx_error(client, headers):
    response = client.get("/employer/search?page_size=100", headers=headers)
    assert response.status_code == 422 and 'role="alert"' in response.text
    response = client.get("/employer/search?page_size=100", headers={**headers, "HX-Request": "true"})
    assert response.status_code == 200 and 'id="matching-results"' in response.text and 'role="alert"' in response.text
    assert '<html' not in response.text
