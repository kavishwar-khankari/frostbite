"""Async Radarr API client."""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class RadarrClient:
    def __init__(self) -> None:
        self._base = settings.radarr_url.rstrip("/")
        self._headers = {"X-Api-Key": settings.radarr_api_key}

    async def _get(self, path: str, **params) -> dict | list:
        url = f"{self._base}/api/v3{path}"
        async with httpx.AsyncClient(headers=self._headers, timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_movies(self) -> list[dict]:
        return await self._get("/movie")

    async def get_movie(self, movie_id: int) -> dict:
        return await self._get(f"/movie/{movie_id}")
