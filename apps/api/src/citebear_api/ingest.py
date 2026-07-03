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
import asyncio
import sys
import uuid
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update

from citebear_api.chunking import chunk_markdown
from citebear_api.db import get_session_factory
from citebear_api.gateway import get_embeddings
from citebear_api.models import Chunk, Document


async def ingest_markdown(path: Path, title: str, source_url: str) -> tuple[uuid.UUID, int]:
    """Ingest one markdown file; returns (document id, chunk count).

    Re-ingesting a file with the same filename replaces the previous
    document (chunks cascade).
    """
    text = path.read_text(encoding="utf-8")
    drafts = chunk_markdown(text)
    if not drafts:
        raise ValueError(f"{path} produced no chunks")

    session_factory = get_session_factory()

    async with session_factory() as session:
        previous = await session.scalars(select(Document.id).where(Document.filename == path.name))
        for previous_id in previous:
            await session.execute(delete(Document).where(Document.id == previous_id))
        document = Document(
            title=title,
            filename=path.name,
            mime_type="text/markdown",
            source_url=source_url,
            status="processing",
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    try:
        vectors = await get_embeddings().aembed_documents([draft.content for draft in drafts])
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


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """asyncio.run with a psycopg-compatible loop on Windows (dev machines)."""
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(coro)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a markdown document")
    parser.add_argument("path", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-url", required=True, help="canonical URL of the original")
    args = parser.parse_args()

    document_id, chunk_count = _run(ingest_markdown(args.path, args.title, args.source_url))
    print(f"ingested {args.path} -> document {document_id} ({chunk_count} chunks)")


if __name__ == "__main__":
    main()
