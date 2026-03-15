"""Async Sonarr API client."""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class SonarrClient:
    def __init__(self) -> None:
        self._base = settings.sonarr_url.rstrip("/")
        self._headers = {"X-Api-Key": settings.sonarr_api_key}

    async def _get(self, path: str, **params) -> dict | list:
        url = f"{self._base}/api/v3{path}"
        async with httpx.AsyncClient(headers=self._headers, timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_series(self) -> list[dict]:
        return await self._get("/series")

    async def get_series_by_tvdb_id(self, tvdb_id: int) -> dict | None:
        series_list = await self.get_series()
        for s in series_list:
            if s.get("tvdbId") == tvdb_id:
                return s
        return None

    async def get_episodes(self, series_id: int) -> list[dict]:
        return await self._get("/episode", seriesId=series_id)
