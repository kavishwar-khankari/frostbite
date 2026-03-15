"""Async Jellyfin REST API client."""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class JellyfinClient:
    def __init__(self) -> None:
        self._base = settings.jellyfin_url.rstrip("/")
        self._headers = {
            "Authorization": f'MediaBrowser Token="{settings.jellyfin_api_key}"',
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, **params) -> dict | list:
        url = f"{self._base}{path}"
        async with httpx.AsyncClient(headers=self._headers, timeout=15) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_item(self, item_id: str) -> dict:
        return await self._get(f"/Items/{item_id}")

    async def get_episodes(self, series_id: str, season_number: int) -> list[dict]:
        data = await self._get(
            f"/Shows/{series_id}/Episodes",
            SeasonIndex=season_number,
            Fields="MediaSources,Path,RunTimeTicks",
        )
        return data.get("Items", [])

    async def find_by_path(self, rel_path: str) -> dict | None:
        """Search Jellyfin for an item whose path ends with rel_path."""
        try:
            data = await self._get(
                "/Items",
                Recursive=True,
                IncludeItemTypes="Movie,Episode",
                Fields="MediaSources,Path,SeriesId,ParentIndexNumber,IndexNumber",
                SearchTerm=rel_path.split("/")[-1],
                Limit=10,
            )
            for item in data.get("Items", []):
                sources = item.get("MediaSources") or []
                for src in sources:
                    if src.get("Path", "").endswith(rel_path):
                        return item
        except httpx.HTTPError as exc:
            logger.warning("Jellyfin find_by_path failed: %s", exc)
        return None

    async def get_all_items(
        self,
        item_types: str = "Movie,Episode",
        fields: str = (
            "MediaSources,SeriesId,SeriesName,"
            "DateCreated,PremiereDate,CommunityRating,"
            "ParentIndexNumber,IndexNumber"
        ),
    ) -> list[dict]:
        """Fetch every Movie and Episode from Jellyfin with pagination (500/page)."""
        all_items: list[dict] = []
        limit = 500
        start = 0
        while True:
            data = await self._get(
                "/Items",
                Recursive=True,
                IncludeItemTypes=item_types,
                Fields=fields,
                StartIndex=start,
                Limit=limit,
            )
            page = data.get("Items") or []
            all_items.extend(page)
            total = data.get("TotalRecordCount", 0)
            start += len(page)
            if not page or start >= total:
                break
        return all_items

    async def get_users(self) -> list[dict]:
        return await self._get("/Users")
