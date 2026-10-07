from typing import Protocol
import httpx

class IdentityProvider(Protocol):
    async def get_profile(self, participant_id: str) -> dict: ...

class FspIdentityClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def get_profile(self, participant_id: str) -> dict:
        response = await self.client.get(f"/participants/{participant_id}")
        response.raise_for_status()
        return response.json()
