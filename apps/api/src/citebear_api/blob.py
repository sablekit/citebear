"""Vercel Blob access (SPEC §3, §5.1).

Uploaded originals live in Blob so the citation viewer can link to the source
document. The api fetches them for ingestion (public URL, no auth) and deletes
them when a document is removed (authenticated with BLOB_READ_WRITE_TOKEN).
"""

import httpx

from citebear_api.config import get_settings

_FETCH_TIMEOUT = 120.0  # a 20 MB original over a slow link still lands in time
_DELETE_URL = "https://blob.vercel-storage.com/delete"


async def fetch_blob(url: str) -> bytes:
    """Download an uploaded original. Blob URLs are public, so no token here."""
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


async def delete_blob(url: str) -> None:
    """Delete a Blob object by URL (SPEC §6: the api owns blob deletion)."""
    token = get_settings().blob_read_write_token
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _DELETE_URL,
            headers={"authorization": f"Bearer {token}"},
            json={"urls": [url]},
        )
        response.raise_for_status()
