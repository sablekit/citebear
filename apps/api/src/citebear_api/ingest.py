"""Document ingestion (SPEC §5.1).

The production path — fetch an uploaded original from Blob, parse by mime type,
chunk, embed, insert — and a local-file CLI wrapper (used to load the self-owned
corpus, the golden set, and the preloaded library). Both share `ingest_document`, which
mirrors the pipeline stages: register the document as processing, embed +
insert, mark ready; on failure mark failed with the reason.

Ingestion runs synchronously within the request (SPEC §5.1): serverless offers
no safe fire-and-forget, so the work is held on the HTTP connection and the
admin UI polls the status the row records.
"""

import argparse
import logging
import uuid
from pathlib import Path

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from citebear_api.blob import delete_blob, fetch_blob, is_blob_url
from citebear_api.chunking import chunk_sections
from citebear_api.db import get_session_factory, run_async
from citebear_api.gateway import embed_texts
from citebear_api.models import Chunk, Document
from citebear_api.parsing import (
    PageLimitError,
    UnsupportedMediaTypeError,
    mime_from_filename,
    parse_document,
)

logger = logging.getLogger(__name__)

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # 20 MB (SPEC §5.1)
MAX_PAGES = 300


class IngestionError(ValueError):
    """A document cannot be ingested; the message is safe to show the admin."""


async def ingest_document(
    *,
    data: bytes,
    filename: str,
    title: str,
    mime_type: str,
    source_url: str,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> tuple[uuid.UUID, int]:
    """Ingest one document's bytes; returns (document id, chunk count).

    Parse and chunk happen before any row is written, so a deterministic input
    error (unsupported type, oversize, no extractable text) is rejected cleanly
    with no orphan row. Only a failure after the document is registered — a
    gateway or database fault mid-embed — flips the row to failed, where the
    admin can see the reason and retry.

    Re-ingesting a file with the same filename replaces the previous document
    only in the same transaction that marks the new one ready, so the old
    version keeps serving if embedding fails partway.
    """
    if len(data) > MAX_DOCUMENT_BYTES:
        raise IngestionError(f"Document exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB limit")

    try:
        # cap pages during parse so an oversized PDF is rejected before it is
        # fully laid out into memory, not after
        sections, page_count = parse_document(data, mime_type, max_pages=MAX_PAGES)
    except (UnsupportedMediaTypeError, IngestionError):
        raise
    except PageLimitError as exc:
        raise IngestionError(f"Document exceeds the {MAX_PAGES}-page limit") from exc
    except Exception as exc:
        # a mislabeled or corrupt file (bytes that don't match the extension)
        # reaches the parser here; surface it as a clean rejection, not a 500
        raise IngestionError("The document could not be parsed; it may be corrupt.") from exc
    drafts = chunk_sections(sections)
    if not drafts:
        raise IngestionError(
            "No extractable text (an image-only PDF needs OCR, which v1 does not do)"
        )

    session_factory = session_factory or get_session_factory()

    async with session_factory() as session:
        document = Document(
            title=title,
            filename=filename,
            mime_type=mime_type,
            source_url=source_url,
            status="processing",
        )
        session.add(document)
        await session.flush()
        document_id = document.id
        await session.commit()

    try:
        # embed outside the write transaction so no DB connection is held across
        # the gateway round trip; batched + bounded-concurrency for large documents
        vectors = await embed_texts([draft.embed_text for draft in drafts])
        async with session_factory() as session:
            session.add_all(
                Chunk(
                    document_id=document_id,
                    ordinal=draft.ordinal,
                    content=draft.content,
                    embedding=vector,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    section_path=draft.section_path,
                    token_count=draft.token_count,
                )
                for draft, vector in zip(drafts, vectors, strict=True)
            )
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="ready", page_count=page_count)
            )
            superseded = list(
                (
                    await session.execute(
                        select(Document.source_url).where(
                            Document.filename == filename, Document.id != document_id
                        )
                    )
                ).scalars()
            )
            await session.execute(
                delete(Document).where(Document.filename == filename, Document.id != document_id)
            )
            await session.commit()
    except Exception as exc:
        async with session_factory() as session:
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", error=str(exc)[:2000])
            )
            await session.commit()
        raise

    # best-effort: delete the replaced originals' blobs so re-ingesting a file
    # doesn't leak the prior upload (preloaded docs keep external URLs, skipped)
    for url in superseded:
        if is_blob_url(url):
            try:
                await delete_blob(url)
            except Exception:
                logger.warning("failed to delete superseded blob on re-ingest")

    return document_id, len(drafts)


async def ingest_from_blob(
    *, blob_url: str, filename: str, title: str, mime_type: str
) -> tuple[uuid.UUID, int]:
    """Fetch an uploaded original from Blob and ingest it. The Blob URL is the
    document's source_url, so the citation viewer links straight to it."""
    # the blobUrl comes from the admin request body; only fetch Vercel Blob URLs
    # so it can't be turned into a server-side fetch of an arbitrary address (SSRF)
    if not is_blob_url(blob_url):
        raise IngestionError("blobUrl must be a Vercel Blob URL")
    try:
        data = await fetch_blob(blob_url)
    except httpx.HTTPError as exc:
        # a fetch fault (timeout, 5xx, a blob deleted by a racing re-ingest) is
        # retryable input trouble, not a server crash — surface it as such
        raise IngestionError("The uploaded file could not be fetched; please retry.") from exc
    return await ingest_document(
        data=data, filename=filename, title=title, mime_type=mime_type, source_url=blob_url
    )


async def ingest_local_file(path: Path, title: str, source_url: str) -> tuple[uuid.UUID, int]:
    """Ingest one local file — the self-owned corpus, the golden set, and the
    preloaded library all load this way. The parser mime is resolved from the
    filename extension (PDF/DOCX/Markdown); anything else is rejected."""
    return await ingest_document(
        data=path.read_bytes(),
        filename=path.name,
        title=title,
        mime_type=mime_from_filename(path.name),
        source_url=source_url,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a local document (PDF/DOCX/Markdown)")
    parser.add_argument("path", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-url", required=True, help="canonical URL of the original")
    args = parser.parse_args()

    document_id, chunk_count = run_async(ingest_local_file(args.path, args.title, args.source_url))
    print(f"ingested {args.path} -> document {document_id} ({chunk_count} chunks)")


if __name__ == "__main__":
    main()
