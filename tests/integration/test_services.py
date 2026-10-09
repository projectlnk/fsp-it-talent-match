import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from app.db.session import engine
from app.integrations.fsp.identity import FspIdentityClient
from app.integrations.fsp.registry import FspRegistryClient

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Set RUN_INTEGRATION=1 with running services")]

def test_database_and_migration():
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
        applied = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        assert applied == set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())

def test_services():
    for base in (os.getenv("APP_BASE_URL", "http://localhost:8000"), os.getenv("FSP_BASE_URL", "http://localhost:8001")):
        assert httpx.get(base + "/docs").status_code == 200
        assert httpx.get(base + "/openapi.json").status_code == 200
    assert httpx.get(os.getenv("APP_BASE_URL", "http://localhost:8000") + "/readiness").json()["database"] == "ok"

def test_integration_clients():
    async def run():
        async with httpx.AsyncClient(base_url=os.getenv("FSP_BASE_URL", "http://localhost:8001"), timeout=5) as client:
            assert (await FspIdentityClient(client).get_profile("demo-1"))["id"] == "demo-1"
            achievements = await FspRegistryClient(client).get_achievements("demo-1")
            assert len(achievements) >= 2
            assert all(a["participant_id"] == "demo-1" for a in achievements)
    # Playwright may keep an event loop running on the pytest main thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, run()).result(timeout=20)


def test_mailpit():
    base = os.getenv("MAILPIT_BASE_URL", "http://mailpit:8025")
    assert httpx.get(base + "/").status_code == 200
    response = httpx.get(base + "/api/v1/messages")
    assert response.status_code == 200
    assert isinstance(response.json()["messages"], list)
