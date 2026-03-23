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

_PAGE_SIZE = 500


class TdarrClient:
    def __init__(self) -> None:
        self._base = settings.tdarr_url.rstrip("/")
        self._headers = {"x-api-key": settings.tdarr_api_key} if settings.tdarr_api_key else {}

    async def get_file_status(self, file_path: str) -> dict | None:
        """
        Query Tdarr for a specific file by its absolute path (used as docID).
        Returns the Tdarr file record or None if not found.
        """
        try:
            async with httpx.AsyncClient(timeout=10, headers=self._headers) as client:
                resp = await client.post(
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
        except Exception as exc:
            logger.debug("Tdarr lookup miss for %s: %s", file_path, exc)
            return None

    async def get_eligible_files(self) -> list[dict]:
        """
        Fetch all files Tdarr considers done using the paginated client/files
        endpoint. Fetches in pages of 500 — much faster than getAll.
        """
        all_files: list[dict] = []

        async with httpx.AsyncClient(timeout=30, headers=self._headers) as client:
            start = 0
            while True:
                resp = await client.post(
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
                )
                if not resp.is_success:
                    raise RuntimeError(
                        f"Tdarr client/files failed {resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()

                # Response format: { files: [...], totalCount: N } or just [...]
                if isinstance(data, dict):
                    files = data.get("files") or data.get("array") or []
                    total = data.get("totalCount", 0)
                elif isinstance(data, list):
                    files = data
                    total = len(files)
                else:
                    break

                all_files.extend(f for f in files if isinstance(f, dict))

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
