"""Tdarr REST API client.

Tdarr tracks every file it knows about in its own database.
Each file has a transcode status — we use this to gate whether
Frostbite is allowed to score or freeze a file.

Relevant transcode statuses Tdarr returns:
  'Not required'      — file already meets the target codec (AV1), eligible
  'Transcoding'       — actively being encoded right now, not eligible
  'Queued'            — waiting in Tdarr's queue, not eligible
  'Failed'            — encode failed, we treat as not eligible until fixed
  'StagedForNextQueue'— about to be queued, not eligible
  ''  / None          — Tdarr hasn't seen this file yet, not eligible
"""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

# These statuses mean Tdarr is done with the file — safe for Frostbite to take over
_ELIGIBLE_STATUSES = {"Not required", "Stream copy"}


class TdarrClient:
    def __init__(self) -> None:
        self._base = settings.tdarr_url.rstrip("/")
        self._headers = {"x-api-key": settings.tdarr_api_key} if settings.tdarr_api_key else {}

    async def get_file_status(self, file_path: str) -> dict | None:
        """
        Query Tdarr for a specific file by its absolute path.
        Returns the Tdarr file record or None if not found.
        """
        try:
            async with httpx.AsyncClient(timeout=10, headers=self._headers) as client:
                resp = await client.post(
                    f"{self._base}/api/v2/cruddb",
                    json={
                        "data": {
                            "collection": "MediaItems",
                            "mode": "find",
                            "docFilter": {"file": file_path},
                            "findLimit": 1,
                        }
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                docs = data.get("docs") or []
                return docs[0] if docs else None
        except httpx.HTTPError as exc:
            logger.warning("Tdarr API error for %s: %s", file_path, exc)
            return None

    async def get_eligible_files(self) -> list[dict]:
        """
        Fetch all files Tdarr considers done (transcode not required or stream copied).
        Used by the scheduler to bulk-update tdarr_eligible flags.
        """
        try:
            async with httpx.AsyncClient(timeout=30, headers=self._headers) as client:
                resp = await client.post(
                    f"{self._base}/api/v2/cruddb",
                    json={
                        "data": {
                            "collection": "MediaItems",
                            "mode": "find",
                            "docFilter": {
                                "TranscodeDecisionMaker": {"$in": list(_ELIGIBLE_STATUSES)}
                            },
                            "limit": 10000,
                        }
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                # Tdarr returns either {array} directly or {docs: array} depending on version
                if isinstance(data, list):
                    return data
                return data.get("docs") or data.get("array") or []
        except httpx.HTTPError as exc:
            logger.warning("Tdarr bulk fetch failed: %s", exc)
            return []

    def is_eligible(self, tdarr_record: dict | None) -> bool:
        """Given a Tdarr file record, return whether Frostbite can manage it."""
        if tdarr_record is None:
            return False
        status = tdarr_record.get("TranscodeDecisionMaker", "")
        return status in _ELIGIBLE_STATUSES
