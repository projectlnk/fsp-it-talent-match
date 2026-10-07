from typing import Protocol
import httpx

class AchievementRegistry(Protocol):
    async def get_achievements(self, participant_id: str) -> list[dict]: ...

class FspRegistryClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def get_achievements(self, participant_id: str) -> list[dict]:
        response = await self.client.get(f"/participants/{participant_id}/achievements")
        response.raise_for_status()
        return response.json()
