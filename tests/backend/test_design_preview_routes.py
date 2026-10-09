"""Read-only prototype route checks: these tests never connect to a database."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_session

SCREENS = ["", "/candidate", "/employer", "/search", "/person/1", "/person/2", "/person/3", "/invitation", "/fsp", "/privacy", "/resume"]

@pytest.fixture
def client():
    def no_database():
        raise AssertionError("Design preview must not depend on a database")
    app.dependency_overrides[get_session] = no_database
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)

@pytest.mark.parametrize("screen", SCREENS)
def test_preview_is_read_only_and_marked(client, screen):
    response = client.get("/design-preview" + screen)
    assert response.status_code == 200
    assert "Демонстрационные данные" in response.text
    assert "ПРОТОТИП" in response.text
    assert client.post("/design-preview" + screen).status_code == 405

@pytest.mark.parametrize("path", ["/design-preview/missing", "/design-preview/person/unknown", "/design-preview/invitation?candidate=unknown"])
def test_preview_unknown_screen_or_person(client, path):
    assert client.get(path).status_code == 404

def test_no_contact_in_initial_candidate_markup(client):
    response = client.get("/design-preview/person/2")
    assert "Скрыты до принятия приглашения" in response.text
    assert 'data-contact-open hidden' in response.text
    assert "Истории ФСП нет" in response.text
