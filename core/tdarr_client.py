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

API reference: /api/v2/cruddb
  collection: FileJSONDB
  modes: getAll, getById, insert, update, removeOne, removeAll
"""

import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

# These statuses mean Tdarr is done with the file — safe for Frostbite to take over.
# "Transcode success" = file was transcoded and succeeded.
# "Not required"     = file already meets the target codec, no transcode needed.
# "Stream copy"      = copied without re-encoding (lightweight transcode).
_ELIGIBLE_STATUSES = {"Transcode success", "Not required", "Stream copy"}


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
                # getById returns the doc directly or null
                if isinstance(data, dict) and data.get("_id"):
                    return data
                return None
        except httpx.HTTPError as exc:
            logger.warning("Tdarr API error for %s: %s", file_path, exc)
            return None

    async def get_eligible_files(self) -> list[dict]:
        """
        Fetch all files Tdarr considers done (transcode not required or stream copied).
        Uses getAll and filters client-side.
        """
        try:
            async with httpx.AsyncClient(timeout=180, headers=self._headers) as client:
                resp = await client.post(
                    f"{self._base}/api/v2/cruddb",
                    json={
                        "data": {
                            "collection": "FileJSONDB",
                            "mode": "getAll",
                        }
                    },
                )
                if not resp.is_success:
                    logger.warning(
                        "Tdarr getAll failed %d: %s",
                        resp.status_code, resp.text[:300],
                    )
                    return []
                data = resp.json()
                if isinstance(data, list):
                    docs = data
                elif isinstance(data, dict):
                    docs = data.get("docs") or data.get("array") or list(data.values())
                else:
                    docs = []
                # Log the distinct status values we see for debugging
                from collections import Counter
                status_counts = Counter(
                    d.get("TranscodeDecisionMaker", "<missing>")
                    for d in docs if isinstance(d, dict)
                )
                logger.info("Tdarr TranscodeDecisionMaker distribution: %s", dict(status_counts))

                eligible = [d for d in docs if isinstance(d, dict)
                            and d.get("TranscodeDecisionMaker") in _ELIGIBLE_STATUSES]
                logger.info("Tdarr eligible files: %d / %d total", len(eligible), len(docs))
                return eligible
        except Exception as exc:
            logger.warning("Tdarr bulk fetch failed (%s): %s", type(exc).__name__, exc)
            raise RuntimeError(f"Tdarr fetch failed ({type(exc).__name__}): {exc}") from exc

    def is_eligible(self, tdarr_record: dict | None) -> bool:
        """Given a Tdarr file record, return whether Frostbite can manage it."""
        if tdarr_record is None:
            return False
        status = tdarr_record.get("TranscodeDecisionMaker", "")
        return status in _ELIGIBLE_STATUSES
