"""Ingestion pre-flight validation.

These reject deterministic input errors before any row is written, so they run
without a database or gateway. The full parse -> embed -> insert round trip is
covered by the golden workflow against a real Postgres.
"""

import asyncio

import httpx
import pytest

from citebear_api import ingest as ingest_module
from citebear_api.ingest import (
    MAX_DOCUMENT_BYTES,
    IngestionError,
    ingest_document,
    ingest_from_blob,
)
from citebear_api.parsing import MARKDOWN_MIME, PDF_MIME, UnsupportedMediaTypeError


def _ingest(data: bytes, mime_type: str) -> None:
    asyncio.run(
        ingest_document(
            data=data,
            filename="doc",
            title="Doc",
            mime_type=mime_type,
            source_url="https://example.test/doc",
        )
    )


def test_oversize_document_is_rejected_before_any_row() -> None:
    with pytest.raises(IngestionError, match="MB limit"):
        _ingest(b"x" * (MAX_DOCUMENT_BYTES + 1), MARKDOWN_MIME)


def test_oversize_is_allowed_when_the_cap_is_lifted() -> None:
    # the trusted CLI path passes max_bytes=None; an over-cap document gets past
    # the size gate (here it fails later on emptiness, proving the gate was skipped
    # rather than the whole ingest short-circuiting)
    with pytest.raises(IngestionError, match="No extractable text"):
        asyncio.run(
            ingest_document(
                data=b" " * (MAX_DOCUMENT_BYTES + 1),
                filename="big.md",
                title="Big",
                mime_type=MARKDOWN_MIME,
                source_url="https://example.test/big",
                max_bytes=None,
                max_pages=None,
            )
        )


def test_unsupported_mime_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        _ingest(b"\x89PNG\r\n", "image/png")


def test_document_with_no_extractable_text_is_rejected() -> None:
    with pytest.raises(IngestionError, match="No extractable text"):
        _ingest(b"   \n\n   ", MARKDOWN_MIME)


def test_corrupt_file_is_rejected_cleanly_not_as_a_crash() -> None:
    # bytes that don't match the declared type reach the parser; it must become a
    # clean IngestionError (-> 422), never an unhandled 500
    with pytest.raises(IngestionError, match="could not be parsed"):
        _ingest(b"this is plainly not a PDF", PDF_MIME)


def test_ingest_from_blob_rejects_non_blob_urls() -> None:
    # the blobUrl comes from the admin body; a non-Blob URL must not be fetched (SSRF)
    with pytest.raises(IngestionError, match="Vercel Blob URL"):
        asyncio.run(
            ingest_from_blob(
                blob_url="http://169.254.169.254/latest/meta-data/",
                filename="x.md",
                title="x",
                mime_type=MARKDOWN_MIME,
            )
        )


def test_blob_fetch_failure_becomes_a_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # a fetch fault (timeout, 5xx, deleted blob) must surface as IngestionError, not a 500
    async def boom(_url: str) -> bytes:
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(ingest_module, "fetch_blob", boom)
    with pytest.raises(IngestionError, match="could not be fetched"):
        asyncio.run(
            ingest_from_blob(
                blob_url="https://x.public.blob.vercel-storage.com/a.md",
                filename="a.md",
                title="a",
                mime_type=MARKDOWN_MIME,
            )
        )
