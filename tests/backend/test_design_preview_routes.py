"""Public overview is separate from operator tools; no fictional screens."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_session
from app.core.config import get_settings

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(),'demo_mode',False)
    class NoDatabase:
        def __getattr__(self,key):
            raise AssertionError('Disabled public demo must not query business data')
    old=app.dependency_overrides.copy()
    app.dependency_overrides[get_session]=lambda:NoDatabase()
    try:
        with TestClient(app) as client:yield client
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(old)

def test_disabled_public_overview(client):
    response=client.get('/design-preview')
    assert response.status_code==200
    assert 'Управление отключено' in response.text
    assert 'data-demo-form' not in response.text
    assert client.post('/design-preview/time',data={'days':'1'}).status_code==404
    assert client.post('/design-preview/sets',data={'password':'demo12345'}).status_code==404

@pytest.mark.parametrize('path',['/candidate','/employer','/search','/person/1','/invitation','/fsp','/privacy','/resume'])
def test_old_fictional_screens_are_not_user_functions(client,path):
    assert client.get('/design-preview'+path).status_code==404
