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
    # what gets embedded — equal to content, except continuation chunks (the 2nd+
    # piece of a split section) carry the section trail so they keep the topical
    # anchor the first piece has from its heading (#7)
    embed_text: str
    token_count: int
    section_path: list[str] = field(default_factory=list[str])
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class Section:
    """A heading-delimited region of a document, before size-splitting.

    The normalized unit every parser (markdown, PDF, DOCX) produces: a heading
    trail plus its body text and the pages that body spans. `chunk_sections`
    turns it into one or more `ChunkDraft`s, splitting oversized bodies without
    crossing the heading boundary. Sources without pages leave the range None.
    """

    section_path: list[str]
    heading_line: str  # e.g. "## Install", reattached to the first chunk; "" if none
    body: str
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
    if budget <= OVERLAP_TOKENS:
        # pathological (sentence-length) heading: reattaching it would
        # shrink the budget below the overlap and crash the splitter
        prefix = ""
        budget = TARGET_TOKENS

    if count_tokens(body) <= budget:
        return [prefix + body]

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING_NAME,
        chunk_size=budget,
        chunk_overlap=OVERLAP_TOKENS,
    )
    pieces = splitter.split_text(body)
    return [prefix + pieces[0], *pieces[1:]] if pieces else []


def chunk_sections(sections: list[Section]) -> list[ChunkDraft]:
    """Split each section's body under the token target, never crossing its
    heading. The section's page range rides onto every chunk it produces —
    coarse for a long split section, but the cited passage always lies within
    it (and most heading-delimited sections fit in one chunk anyway)."""
    drafts: list[ChunkDraft] = []
    for section in sections:
        body = section.body.strip()
        if not body:
            continue
        trail = " > ".join(section.section_path)
        for piece_index, piece in enumerate(_split_section(section.heading_line, body)):
            content = piece.strip()
            if not content:
                continue
            # the first piece already carries the heading; continuation pieces
            # get the trail prepended for embedding only (#7)
            embed_text = f"{trail}\n\n{content}" if piece_index and trail else content
            drafts.append(
                ChunkDraft(
                    ordinal=len(drafts),
                    content=content,
                    embed_text=embed_text,
                    token_count=count_tokens(content),
                    section_path=section.section_path,
                    page_start=section.page_start,
                    page_end=section.page_end,
                )
            )
    return drafts


def markdown_sections(text: str) -> list[Section]:
    """Split markdown into heading-delimited sections (no page numbers)."""
    header_splitter = MarkdownHeaderTextSplitter(_HEADERS, strip_headers=True)

    sections: list[Section] = []
    for section in header_splitter.split_text(text):
        section_path = [
            str(section.metadata[key]) for _, key in _HEADERS if key in section.metadata
        ]
        heading_line = ""
        for marker, key in reversed(_HEADERS):
            if key in section.metadata:
                heading_line = f"{marker} {section.metadata[key]}"
                break
        sections.append(
            Section(section_path=section_path, heading_line=heading_line, body=section.page_content)
        )
    return sections


def chunk_markdown(text: str) -> list[ChunkDraft]:
    return chunk_sections(markdown_sections(text))
