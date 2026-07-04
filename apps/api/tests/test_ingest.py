"""Ingestion pre-flight validation.

These reject deterministic input errors before any row is written, so they run
without a database or gateway. The full parse -> embed -> insert round trip is
covered by the golden workflow against a real Postgres.
"""

import asyncio

import pytest

from citebear_api.ingest import MAX_DOCUMENT_BYTES, IngestionError, ingest_document
from citebear_api.parsing import MARKDOWN_MIME, UnsupportedMediaTypeError


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


def test_unsupported_mime_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        _ingest(b"\x89PNG\r\n", "image/png")


def test_document_with_no_extractable_text_is_rejected() -> None:
    with pytest.raises(IngestionError, match="No extractable text"):
        _ingest(b"   \n\n   ", MARKDOWN_MIME)
