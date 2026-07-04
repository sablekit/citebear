"""Load the preloaded library into the database (SPEC §11).

Fetches each document in the manifest from its canonical URL and ingests it via
the trusted CLI path (no upload size/page caps). Run once against the target
database to populate a fresh instance:

    uv run python -m citebear_api.load_library

Re-running replaces each document by filename (the ingest transaction supersedes
the prior version only once the new one is ready).
"""

import httpx

from citebear_api.db import run_async
from citebear_api.ingest import ingest_document
from citebear_api.parsing import mime_from_filename
from citebear_api.preloaded import LIBRARY

# the Debian handbook is ~22 MB; give the fetch generous headroom
_FETCH_TIMEOUT = httpx.Timeout(180.0)


async def load_library() -> None:
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
        for doc in LIBRARY:
            print(f"fetching {doc.source_url} ...")
            response = await client.get(doc.source_url)
            response.raise_for_status()
            document_id, chunk_count = await ingest_document(
                data=response.content,
                filename=doc.filename,
                title=doc.title,
                mime_type=mime_from_filename(doc.filename),
                source_url=doc.source_url,
                max_bytes=None,
                max_pages=None,
            )
            print(f"  -> {doc.title}: document {document_id} ({chunk_count} chunks)")


def main() -> None:
    run_async(load_library())


if __name__ == "__main__":
    main()
