"""Structure-preserving chunking (SPEC §5.1).

Structure-first, not fixed-window: split on heading boundaries, then
recursively split oversized sections targeting ~400 tokens with ~15%
overlap, never crossing a heading boundary. The section trail rides
along as metadata — it is what makes citations precise.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

TARGET_TOKENS = 400
OVERLAP_TOKENS = 60  # ~15% of target
ENCODING_NAME = "cl100k_base"

_HEADERS: list[tuple[str, str]] = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]


@dataclass(frozen=True)
class ChunkDraft:
    """A chunk ready for embedding; mirrors the chunks table minus the vector."""

    ordinal: int
    content: str
    token_count: int
    section_path: list[str] = field(default_factory=list[str])
    page_start: int | None = None
    page_end: int | None = None


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING_NAME)


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


def _split_section(heading_line: str, body: str) -> list[str]:
    """Split one section's body, reattaching the heading to the first piece.

    Splitting the heading together with the body would strand it as a
    tiny standalone chunk (the recursive splitter flushes short leading
    splits), so the body is split alone and the heading is prepended
    afterwards. The size budget shrinks by the heading so no piece
    exceeds the target.
    """
    prefix = f"{heading_line}\n\n" if heading_line else ""
    budget = TARGET_TOKENS - count_tokens(prefix)

    if count_tokens(body) <= budget:
        return [prefix + body]

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING_NAME,
        chunk_size=budget,
        chunk_overlap=OVERLAP_TOKENS,
    )
    pieces = splitter.split_text(body)
    return [prefix + pieces[0], *pieces[1:]] if pieces else []


def chunk_markdown(text: str) -> list[ChunkDraft]:
    header_splitter = MarkdownHeaderTextSplitter(_HEADERS, strip_headers=True)

    drafts: list[ChunkDraft] = []
    for section in header_splitter.split_text(text):
        section_path = [
            str(section.metadata[key]) for _, key in _HEADERS if key in section.metadata
        ]
        heading_line = ""
        for marker, key in reversed(_HEADERS):
            if key in section.metadata:
                heading_line = f"{marker} {section.metadata[key]}"
                break

        body = section.page_content.strip()
        if not body:
            continue
        for piece in _split_section(heading_line, body):
            content = piece.strip()
            if not content:
                continue
            drafts.append(
                ChunkDraft(
                    ordinal=len(drafts),
                    content=content,
                    token_count=count_tokens(content),
                    section_path=section_path,
                )
            )
    return drafts
