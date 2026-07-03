"""Markdown ingestion command (Milestone 1: the hardcoded library).

Usage:
    uv run python -m citebear_api.ingest docs/SPEC.md \
        --title "CiteBear Specification" \
        --source-url https://github.com/sablekit/citebear/blob/main/docs/SPEC.md

Mirrors the production pipeline stages (SPEC §5.1): register the document
as processing, parse + chunk, embed batched, insert chunks, mark ready —
with a failed status and error message on any failure.
"""

import argparse
import uuid
from pathlib import Path

from sqlalchemy import delete, update

from citebear_api.chunking import chunk_markdown
from citebear_api.db import get_session_factory, run_async
from citebear_api.gateway import get_embeddings
from citebear_api.models import Chunk, Document


async def ingest_markdown(path: Path, title: str, source_url: str) -> tuple[uuid.UUID, int]:
    """Ingest one markdown file; returns (document id, chunk count).

    Re-ingesting a file with the same filename replaces the previous
    document only in the same transaction that marks the new one ready,
    so the old version keeps serving if embedding fails partway.
    """
    text = path.read_text(encoding="utf-8")
    drafts = chunk_markdown(text)
    if not drafts:
        raise ValueError(f"{path} produced no chunks")

    session_factory = get_session_factory()

    async with session_factory() as session:
        document = Document(
            title=title,
            filename=path.name,
            mime_type="text/markdown",
            source_url=source_url,
            status="processing",
        )
        session.add(document)
        await session.flush()
        document_id = document.id
        await session.commit()

    try:
        vectors = await get_embeddings().aembed_documents([draft.embed_text for draft in drafts])
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
                update(Document).where(Document.id == document_id).values(status="ready")
            )
            await session.execute(
                delete(Document).where(Document.filename == path.name, Document.id != document_id)
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

    return document_id, len(drafts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a markdown document")
    parser.add_argument("path", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-url", required=True, help="canonical URL of the original")
    args = parser.parse_args()

    document_id, chunk_count = run_async(ingest_markdown(args.path, args.title, args.source_url))
    print(f"ingested {args.path} -> document {document_id} ({chunk_count} chunks)")


if __name__ == "__main__":
    main()
