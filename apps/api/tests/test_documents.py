"""Document endpoint tests: pure helpers, camelCase serialization, admin auth.

The full register/list/delete round trip needs a real Postgres (SPEC §9
integration) and is exercised against docker-compose / the golden workflow DB;
these cover the logic reachable without one.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from citebear_api.app import app
from citebear_api.blob import is_blob_url
from citebear_api.documents import AdminDocumentOut
from citebear_api.parsing import (
    DOCX_MIME,
    MARKDOWN_MIME,
    PDF_MIME,
    UnsupportedMediaTypeError,
    mime_from_filename,
)

ADMIN_HEADER = {"Authorization": "Bearer test-admin-password"}  # matches conftest env


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("manual.pdf", PDF_MIME),
        ("report.PDF", PDF_MIME),
        ("notes.docx", DOCX_MIME),
        ("readme.md", MARKDOWN_MIME),
        ("readme.markdown", MARKDOWN_MIME),
    ],
)
def test_mime_from_filename_maps_supported_extensions(filename: str, expected: str) -> None:
    assert mime_from_filename(filename) == expected


@pytest.mark.parametrize("filename", ["image.png", "sheet.xlsx", "noext", "archive.zip"])
def test_mime_from_filename_rejects_others(filename: str) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        mime_from_filename(filename)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://abc123.public.blob.vercel-storage.com/doc.pdf", True),
        ("https://blob.vercel-storage.com/doc.pdf", True),
        ("https://github.com/sablekit/citebear/blob/main/docs/SPEC.md", False),
        ("https://evil-blob.vercel-storage.com.attacker.test/x", False),
    ],
)
def test_is_blob_url(url: str, expected: bool) -> None:
    assert is_blob_url(url) is expected


def test_admin_document_serializes_camelcase_from_attributes() -> None:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        title="Calibre Manual",
        filename="calibre.pdf",
        mime_type=PDF_MIME,
        source_url="https://x.public.blob.vercel-storage.com/calibre.pdf",
        page_count=42,
        status="ready",
        error=None,
        created_at=datetime.now(UTC),
    )
    payload = AdminDocumentOut.model_validate(row).model_dump(by_alias=True)
    assert payload["mimeType"] == PDF_MIME
    assert payload["sourceUrl"].endswith("calibre.pdf")
    assert payload["pageCount"] == 42
    assert payload["status"] == "ready"
    assert "createdAt" in payload


def test_admin_routes_reject_missing_credentials() -> None:
    client = TestClient(app)
    doc_id = str(uuid.uuid4())
    body = {
        "blobUrl": "https://x.public.blob.vercel-storage.com/a.pdf",
        "filename": "a.pdf",
        "title": "A",
    }

    unauth = [
        client.get("/admin/documents"),
        client.post("/admin/documents", json=body),
        client.delete(f"/admin/documents/{doc_id}"),
    ]
    for response in unauth:
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")


def test_admin_routes_reject_wrong_password() -> None:
    client = TestClient(app)
    response = client.get("/admin/documents", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
