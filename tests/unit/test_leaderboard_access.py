"""Small route checks without a database or browser stack."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app, page_error
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import UserRole
from app.modules.career import web


@pytest.mark.parametrize('role,verified', [
    (UserRole.EMPLOYER, False), (UserRole.EMPLOYER, True), (UserRole.CANDIDATE, True),
])
def test_leaderboard_keeps_authenticated_identity(monkeypatch, role, verified):
    user = SimpleNamespace(id=42, role=role, email='test@example.invalid', is_email_verified=verified)
    monkeypatch.setattr(web.s, 'process_due', lambda db: None)
    monkeypatch.setattr(web.s, 'leaderboard', lambda db: [])
    old_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: MagicMock()
    try:
        response = TestClient(app).get('/career/leaderboard')
        assert response.status_code == 200
        assert 'data-auth-user="42"' in response.text
        assert 'test@example.invalid' in response.text
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


def test_career_denial_does_not_clear_authenticated_identity(monkeypatch):
    from app.db import session
    from app.modules.auth import dependencies
    user = SimpleNamespace(id=42, role=UserRole.EMPLOYER, email='test@example.invalid')
    monkeypatch.setattr(session, 'SessionLocal', MagicMock())
    monkeypatch.setattr(dependencies, 'get_current_user_optional', lambda *args, **kwargs: user)
    request = Request({'type':'http', 'method':'GET', 'scheme':'http', 'server':('testserver',80),
                       'path':'/career/leaderboard', 'root_path':'', 'query_string':b'',
                       'headers':[(b'accept',b'text/html')], 'app':app})
    response = asyncio.run(page_error(request, HTTPException(403, 'Подтвердите email')))
    assert response.status_code == 403
    assert b'data-auth-user="42"' in response.body
    assert b'href="/employer/profile"' in response.body
