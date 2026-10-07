from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.main import app
from app.db.session import get_session
from mock_fsp.main import app as mock_app

def test_app_smoke():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        assert "/readiness" in client.get("/openapi.json").json()["paths"]
        assert client.get("/").status_code == 200
        for path in ("css/main.css", "js/main.js", "vendor/htmx.min.js"):
            assert client.get("/static/" + path).status_code == 200

def test_readiness_failure():
    class Unavailable:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("unavailable"))
    app.dependency_overrides[get_session] = lambda: Unavailable()
    try:
        with TestClient(app) as client:
            assert client.get("/readiness").status_code == 503
    finally:
        app.dependency_overrides.clear()

def test_mock_smoke():
    with TestClient(mock_app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/participants/demo-1").json()["id"] == "demo-1"
        assert client.get("/participants/demo-1/achievements").json()[0]["participant_id"] == "demo-1"
        assert client.get("/participants/demo-2/achievements").json() == []
        assert client.get("/participants/missing").status_code == 404
