import asyncio
import httpx
import pytest
from app.integrations.fsp.identity import FspIdentityClient
from app.integrations.fsp.registry import FspRegistryClient
from mock_fsp.main import app

def test_clients_against_mock():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock-fsp", timeout=5) as client:
            assert (await FspIdentityClient(client).get_profile("demo-1"))["id"] == "demo-1"
            assert len(await FspRegistryClient(client).get_achievements("demo-1")) == 1
            assert await FspRegistryClient(client).get_achievements("demo-2") == []
            with pytest.raises(httpx.HTTPStatusError) as error:
                await FspIdentityClient(client).get_profile("missing")
            assert error.value.response.status_code == 404
    asyncio.run(run())
