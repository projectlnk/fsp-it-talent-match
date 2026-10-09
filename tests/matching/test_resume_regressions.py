"""PDF HTML must preserve literal user text and report real assessment status."""
import sys
from types import SimpleNamespace
from sqlalchemy.orm import Session
from app.modules.candidates import resume
from app.modules.candidates.models import CandidateProfile


def test_pdf_escapes_text_and_preserves_zero_and_unconfirmed_status(database, monkeypatch):
    rendered = []
    class HTML:
        def __init__(self, *, string):
            rendered.append(string)
        def write_pdf(self):
            return b'%PDF-test'
    monkeypatch.setitem(sys.modules, 'weasyprint', SimpleNamespace(HTML=HTML))
    with Session(database[0]) as session:
        profile = session.get(CandidateProfile, database[1]['profiles'][5].id)
        profile.about = '<img src="file:///etc/passwd">Буквальный текст'
        profile.desired_salary_from = 0
        profile.desired_salary_to = 0
        session.commit()
        assert resume.generate_resume_pdf(session, user_id=profile.user_id) == b'%PDF-test'
    html = rendered[0]
    assert '<img src=' not in html and '&lt;img src=' in html
    assert '0–0 ₽' in html
    assert 'Категория не подтверждена.' in html
    assert 'Грейд подтверждён платформой.' not in html
    assert 'История тестирования' in html


def test_pdf_generation_failure_is_visible(client, candidate_headers, monkeypatch):
    def fail(*args, **kwargs):
        raise resume.ResumeError('test failure')
    monkeypatch.setattr(resume, 'generate_resume_pdf', fail)
    result = client.get('/candidate/profile/resume.pdf', headers=candidate_headers)
    assert result.status_code == 503
    assert 'Не удалось сформировать PDF.' in result.text
    assert 'text/html' in result.headers['content-type']
