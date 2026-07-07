"""Document endpoints (SPEC §6): admin register/list/delete + public list.

Registration ingests synchronously within the request (SPEC §5.1) and returns
the resulting row — ready on success, or a Problem if the input is rejected.
The admin list reports every status so the UI can reflect processing/failed
across reloads; the public list is ready-only (the chat's available sources).
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select

from citebear_api.auth import require_admin, require_internal_key
from citebear_api.blob import delete_blob, is_blob_url
from citebear_api.db import get_session_factory
from citebear_api.ingest import IngestionError, ingest_from_blob
from citebear_api.models import Document
from citebear_api.parsing import UnsupportedMediaTypeError, mime_from_filename
from citebear_api.preloaded import attribution_for

logger = logging.getLogger(__name__)

router = APIRouter()


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class RegisterDocumentRequest(_CamelModel):
    blob_url: str
    filename: str
    title: str


class AttributionOut(_CamelModel):
    """Credit for a preloaded source document (SPEC §11); absent for uploads."""

    authors: str
    license_name: str
    license_url: str


class DocumentOut(_CamelModel):
    """Public shape: a ready document the chat can cite."""

    id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    source_url: str
    page_count: int | None
    attribution: AttributionOut | None = None


class AdminDocumentOut(DocumentOut):
    """Admin shape: adds the ingestion status the documents tab polls."""

    status: str
    error: str | None
    created_at: datetime


def to_document_out[M: DocumentOut](model_cls: type[M], row: Document) -> M:
    """Serialize a document row, attaching preloaded-library attribution when the
    source_url is one the manifest covers."""
    out = model_cls.model_validate(row)
    attribution = attribution_for(row.source_url)
    if attribution is not None:
        out.attribution = AttributionOut.model_validate(attribution)
    return out


@router.get("/documents", dependencies=[Depends(require_internal_key)])
async def list_documents() -> list[DocumentOut]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                select(Document).where(Document.status == "ready").order_by(Document.title)
            )
        ).scalars()
        return [to_document_out(DocumentOut, row) for row in rows]


@router.get(
    "/admin/documents",
    dependencies=[Depends(require_internal_key), Depends(require_admin)],
)
async def list_admin_documents() -> list[AdminDocumentOut]:
    async with get_session_factory()() as session:
        rows = (
            await session.execute(select(Document).order_by(Document.created_at.desc()))
        ).scalars()
        return [to_document_out(AdminDocumentOut, row) for row in rows]


@router.post(
    "/admin/documents",
    dependencies=[Depends(require_internal_key), Depends(require_admin)],
    status_code=status.HTTP_201_CREATED,
)
async def register_document(body: RegisterDocumentRequest) -> AdminDocumentOut:
    try:
        mime_type = mime_from_filename(body.filename)
        document_id, _ = await ingest_from_blob(
            blob_url=body.blob_url,
            filename=body.filename,
            title=body.title,
            mime_type=mime_type,
        )
    except UnsupportedMediaTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOCX, and Markdown documents are supported.",
        ) from exc
    except IngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    async with get_session_factory()() as session:
        document = await session.get(Document, document_id)
        if document is None:
            # a concurrent re-ingest of the same filename removed it between the
            # commit and this read; report it rather than crash on a bare assert
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The document was replaced concurrently; please retry.",
            )
        return to_document_out(AdminDocumentOut, document)


@router.delete(
    "/admin/documents/{document_id}",
    dependencies=[Depends(require_internal_key), Depends(require_admin)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_document(document_id: uuid.UUID) -> Response:
    async with get_session_factory()() as session:
        document = await session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        source_url = document.source_url
        await session.delete(document)  # ON DELETE CASCADE drops its chunks + citations
        await session.commit()

    # Delete the blob after the row is gone: an orphaned blob is a harmless
    # storage leak, but a live row pointing at a deleted blob is a broken
    # citation link. Only uploads live in Blob — preloaded docs keep external
    # URLs. Best-effort: the document is already gone as far as the user cares.
    if is_blob_url(source_url):
        try:
            await delete_blob(source_url)
        except Exception:
            logger.warning("failed to delete blob for removed document %s", document_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
