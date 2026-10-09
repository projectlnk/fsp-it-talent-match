"""Refuse data-writing integration/E2E checks against an unverified application stack."""
import os
import subprocess
from urllib.parse import urlsplit
import pytest
from sqlalchemy.engine import make_url

@pytest.fixture(autouse=True, scope="session")
def isolated_external_stack(request):
    # Local matching tests override get_session and own fresh databases instead.
    selected = [item for item in request.session.items if
                ("/integration/" in item.nodeid.replace("\\", "/") and os.getenv("RUN_INTEGRATION") == "1")
                or ("/e2e/" in item.nodeid.replace("\\", "/") and
                    any(name in item.nodeid for name in ("auth_flow", "matching_flow", "matching_search"))
                    and os.getenv("RUN_E2E") == "1")]
    if not selected:
        return
    project = os.getenv("TEST_COMPOSE_PROJECT", "")
    if not project.startswith("fsp-matching-check-"):
        pytest.fail("Writing checks require an explicit isolated TEST_COMPOSE_PROJECT")
    url = make_url(os.getenv("DATABASE_URL", ""))
    if url.get_backend_name() != "postgresql" or url.database != "fsp_matching_test":
        pytest.fail("Writing checks require DATABASE_URL pointing to fsp_matching_test")
    def port(service, internal):
        result = subprocess.run(["docker", "compose", "-f", "compose.test.yaml", "-p", project,
                                 "port", service, str(internal)], capture_output=True, text=True, check=True)
        return int(result.stdout.strip().rsplit(":", 1)[1])
    base = urlsplit(os.getenv("APP_BASE_URL", ""))
    if base.hostname not in {"127.0.0.1", "localhost"} or base.port != port("app", 8000):
        pytest.fail("APP_BASE_URL must reference the isolated Compose app")
    if url.host not in {"127.0.0.1", "localhost"} or url.port != port("db", 5432):
        pytest.fail("DATABASE_URL must reference the isolated Compose PostgreSQL")
