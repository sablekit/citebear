"""Database schema (SPEC §4).

snake_case, plural tables, singular columns, timestamptz UTC,
gen_random_uuid() primary keys. Migrations live in migrations/.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import Computed, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import ARRAY, REAL, TIMESTAMP, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Boolean, Integer, Text

EMBEDDING_DIM = 1536  # text-embedding-3-small; changing models requires re-ingestion


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # processing | ready | failed
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # generated tsvector for keyword search; never read into Python (excluded
    # from selects), the Mapped[str] annotation just makes it queryable + typed
    fts: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    token_count: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index(
            "idx_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_chunks_fts", "fts", postgresql_using="gin"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    role: Mapped[str] = mapped_column(Text)  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)  # user rows: for rate limiting
    grounded: Mapped[bool | None] = mapped_column(Boolean)  # assistant: false = refused
    confidence: Mapped[str | None] = mapped_column(Text)  # assistant: high | low
    model: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_messages_session_id_created_at", "session_id", "created_at"),
        Index("idx_messages_ip_hash_created_at", "ip_hash", "created_at"),
    )


class MessageCitation(Base):
    __tablename__ = "message_citations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    marker: Mapped[int] = mapped_column(Integer, primary_key=True)  # [1], [2], ... in the answer
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE")
    )
    # rerank score in Milestone 3; vector similarity (1 - cosine_distance) until then
    score: Mapped[float] = mapped_column(REAL)
