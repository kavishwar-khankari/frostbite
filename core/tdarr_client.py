"""Tdarr REST API client.

Tdarr tracks every file it knows about in its own database (FileJSONDB).
Each file has a transcode status — we use this to gate whether
Frostbite is allowed to score or freeze a file.

Relevant transcode statuses Tdarr returns:
  'Not required'      — file already meets the target codec (AV1), eligible
  'Transcoding'       — actively being encoded right now, not eligible
  'Queued'            — waiting in Tdarr's queue, not eligible
  'Failed'            — encode failed, we treat as not eligible until fixed
  'StagedForNextQueue'— about to be queued, not eligible
  ''  / None          — Tdarr hasn't seen this file yet, not eligible

API reference:
  /api/v2/cruddb       — low-level CRUD (getById, getAll, etc.)
  /api/v2/client/files — paginated, filterable file table (used by Tdarr UI)
"""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

# These statuses mean Tdarr is done with the file — safe for Frostbite to take over.
_ELIGIBLE_STATUSES = {"Transcode success", "Not required", "Stream copy"}

# Tdarr UI table name for the "Transcode: Success/Not Required" tab
_TABLE_TRANSCODE_SUCCESS = "table2"

_PAGE_SIZE = 100


class TdarrClient:
    def __init__(self) -> None:
        self._base = settings.tdarr_url.rstrip("/")
        self._headers = {"x-api-key": settings.tdarr_api_key} if settings.tdarr_api_key else {}

    async def get_file_status(self, file_path: str, client: httpx.AsyncClient | None = None) -> dict | None:
        """
        Query Tdarr for a specific file by its absolute path (used as docID).
        Returns the Tdarr file record or None if not found.
        Accepts an optional shared httpx client for batch use.
        """
        try:
            c = client or httpx.AsyncClient(timeout=10, headers=self._headers)
            try:
                resp = await c.post(
                    f"{self._base}/api/v2/cruddb",
                    json={
                        "data": {
                            "collection": "FileJSONDB",
                            "mode": "getById",
                            "docID": file_path,
                        }
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("_id"):
                    return data
                return None
            finally:
                if client is None:
                    await c.aclose()
        except Exception as exc:
            logger.debug("Tdarr lookup miss for %s: %s", file_path, exc)
            return None

    async def get_eligible_files(self) -> list[dict]:
        """
        Fetch all files Tdarr considers done using the paginated status-tables
        endpoint. Uses streaming to handle large response bodies (~14 KB/item).
        """
        all_files: list[dict] = []
        import json as _json

        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=300), headers=self._headers) as client:
            start = 0
            while True:
                async with client.stream(
                    "POST",
                    f"{self._base}/api/v2/client/status-tables",
                    json={
                        "data": {
                            "start": start,
                            "pageSize": _PAGE_SIZE,
                            "filters": [],
                            "sorts": [],
                            "opts": {
                                "table": _TABLE_TRANSCODE_SUCCESS,
                            },
                        }
                    },
                ) as resp:
                    if not resp.is_success:
                        body = (await resp.aread()).decode()
                        raise RuntimeError(
                            f"Tdarr status-tables failed {resp.status_code}: {body[:300]}"
                        )
                    chunks = []
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                    data = _json.loads(b"".join(chunks))

                if isinstance(data, dict):
                    files = data.get("array") or data.get("files") or []
                    total = data.get("totalCount", 0)
                elif isinstance(data, list):
                    files = data
                    total = len(files)
                else:
                    break

                all_files.extend(f for f in files if isinstance(f, dict))
                logger.info("Tdarr page start=%d: got %d files, totalCount=%d", start, len(files), total)

                start += _PAGE_SIZE
                if start >= total or not files:
                    break

        logger.info("Tdarr eligible files: %d fetched from paginated API", len(all_files))
        return all_files

    def is_eligible(self, tdarr_record: dict | None) -> bool:
        """Given a Tdarr file record, return whether Frostbite can manage it."""
        if tdarr_record is None:
            return False
        status = tdarr_record.get("TranscodeDecisionMaker", "")
        return status in _ELIGIBLE_STATUSES
