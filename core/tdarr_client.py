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

# Two body shapes to try — Tdarr versions disagree on whether the payload
# lives under a "data" key or at the top level.
def _build_bodies(collection: str, doc_filter: dict, limit: int) -> list[dict]:
    inner = {
        "collection": collection,
        "mode": "find",
        "docFilter": doc_filter,
        "limit": limit,
    }
    return [
        {"data": inner},  # newer Tdarr versions
        inner,            # older / alternate versions
    ]


class TdarrClient:
    def __init__(self) -> None:
        self._base = settings.tdarr_url.rstrip("/")
        self._headers = {"x-api-key": settings.tdarr_api_key} if settings.tdarr_api_key else {}

    async def _cruddb(self, doc_filter: dict, limit: int) -> list[dict]:
        """
        POST to /api/v2/cruddb, trying both body shapes.
        Returns the list of documents or [] on failure.
        """
        url = f"{self._base}/api/v2/cruddb"
        bodies = _build_bodies("MediaItems", doc_filter, limit)
        async with httpx.AsyncClient(timeout=60, headers=self._headers) as client:
            for body in bodies:
                try:
                    resp = await client.post(url, json=body)
                    if resp.status_code == 400:
                        logger.debug("Tdarr cruddb 400 with body shape %s: %s", body.keys(), resp.text[:200])
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    return data.get("docs") or data.get("array") or []
                except httpx.HTTPStatusError as exc:
                    logger.warning("Tdarr cruddb error (shape=%s): %s — %s",
                                   list(body.keys()), exc, exc.response.text[:200])
                except httpx.HTTPError as exc:
                    logger.warning("Tdarr cruddb request failed: %s", exc)
                    return []
        logger.warning("Tdarr cruddb: all body shapes returned 400")
        return []

    async def get_file_status(self, file_path: str) -> dict | None:
        """Query Tdarr for a specific file. Returns the record or None."""
        docs = await self._cruddb({"file": file_path}, limit=1)
        return docs[0] if docs else None

    async def get_eligible_files(self) -> list[dict]:
        """
        Fetch all files Tdarr considers done (transcode not required or stream copied).
        Fetches all items and filters client-side to avoid NeDB query operator issues.
        """
        docs = await self._cruddb({}, limit=100000)
        return [d for d in docs if d.get("TranscodeDecisionMaker") in _ELIGIBLE_STATUSES]

    def is_eligible(self, tdarr_record: dict | None) -> bool:
        """Given a Tdarr file record, return whether Frostbite can manage it."""
        if tdarr_record is None:
            return False
        status = tdarr_record.get("TranscodeDecisionMaker", "")
        return status in _ELIGIBLE_STATUSES
