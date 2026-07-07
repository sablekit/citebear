"""Document parsers: PDF / DOCX / Markdown -> normalized sections (SPEC §5.1).

Each parser reduces a document to an ordered block stream (headings + body
paragraphs, each with a page number where the format has one), which a shared
heading-stack fold turns into `Section`s. Those feed the single structure-aware
chunker in `chunking.py`, so citation metadata (section trail, page range) is
produced the same way regardless of source format.

PDF uses **pdfminer.six** (MIT) — font-size and weight heuristics recover a
heading hierarchy PDFs don't store explicitly. DOCX uses **python-docx**,
reading the heading styles Word records. Markdown reuses the header-splitter
path.
"""

import io
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import cast

from docx import Document as DocxDocument
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTTextContainer, LTTextLine

from citebear_api.chunking import Section, markdown_sections

MARKDOWN_MIME = "text/markdown"
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_EXTENSION_MIME = {
    ".pdf": PDF_MIME,
    ".docx": DOCX_MIME,
    ".md": MARKDOWN_MIME,
    ".markdown": MARKDOWN_MIME,
}

MAX_HEADING_LEVEL = 4  # mirrors the markdown splitter (h1..h4)
# a line whose font is this much larger than the body's is treated as a heading
HEADING_SIZE_RATIO = 1.15
# a fully-bold line no longer than this (in words) is treated as a heading even
# at body size — manuals often set same-size bold headings that font size alone
# would miss
BOLD_HEADING_MAX_WORDS = 12


def _line_is_bold(fonts: list[str]) -> bool:
    """True when every glyph on a line uses a bold font face (a partly-bold line
    is inline emphasis, not a heading)."""
    return bool(fonts) and all("bold" in font.lower() for font in fonts)


def _bold_heading_like(text: str) -> bool:
    """A short, fully-bold line that doesn't read like a sentence is very likely
    a body-size heading rather than emphasized prose. A trailing sentence
    terminator (. ? !) marks prose; a trailing colon still reads as a heading."""
    return len(text.split()) <= BOLD_HEADING_MAX_WORDS and not text.endswith((".", "?", "!"))


class UnsupportedMediaTypeError(ValueError):
    """The upload's mime type has no parser (e.g. an image, a spreadsheet)."""


class PageLimitError(ValueError):
    """A PDF has more pages than the ingestion cap allows.

    Raised mid-parse so an oversized document is rejected the moment it crosses
    the cap, without laying out the remaining hundreds of pages into memory.
    """


def mime_from_filename(filename: str) -> str:
    """Resolve the parser mime from a filename extension (uploads carry only a
    filename, SPEC §6); raises for anything without a parser."""
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in _EXTENSION_MIME:
        raise UnsupportedMediaTypeError(filename)
    return _EXTENSION_MIME[suffix]


@dataclass(frozen=True)
class Block:
    """One unit of a parsed document: a heading (level 1..N) or body (level None)."""

    text: str
    level: int | None
    page: int | None


def _assemble_sections(blocks: list[Block], body_separator: str = "\n\n") -> list[Section]:
    """Fold a block stream into heading-delimited sections.

    A heading pops the stack back to its level and pushes itself; the body
    paragraphs after it accumulate into one section carrying the full heading
    trail and the page span of its content. Body before the first heading
    becomes a section with an empty trail (the document preamble).
    """
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []
    path: list[str] = []
    heading_line = ""
    body: list[str] = []
    pages: list[int] = []

    def flush() -> None:
        if not body:
            return
        sections.append(
            Section(
                section_path=list(path),
                heading_line=heading_line,
                body=body_separator.join(body),
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
            )
        )

    for block in blocks:
        if block.level is None:
            body.append(block.text)
            if block.page is not None:
                pages.append(block.page)
            continue
        flush()
        body = []
        pages = [block.page] if block.page is not None else []  # heading seeds the range
        while stack and stack[-1][0] >= block.level:
            stack.pop()
        stack.append((block.level, block.text))
        path = [text for _, text in stack]
        heading_line = f"{'#' * min(block.level, MAX_HEADING_LEVEL)} {block.text}"
    flush()
    return sections


def parse_pdf(data: bytes, max_pages: int | None = None) -> tuple[list[Section], int]:
    """Parse a PDF into sections, recovering headings from font sizes.

    Uses pdfminer.six directly (rather than pdfplumber, which drags in
    pypdfium2 + Pillow we don't use) — text lines carry their per-glyph font
    size and font name (`LTChar.size` / `.fontname`), which is all the
    size-plus-weight heading heuristic needs.

    `extract_pages` is lazy, so passing `max_pages` lets an oversized document
    be rejected (via `PageLimitError`) the moment it crosses the cap, before
    the remaining pages are laid out.
    """
    lines: list[tuple[str, float, bool, int]] = []  # (text, rounded size, bold, page)
    page_count = 0
    for page_number, page_layout in enumerate(extract_pages(io.BytesIO(data)), start=1):
        if max_pages is not None and page_number > max_pages:
            raise PageLimitError(page_number)
        page_count = page_number
        for element in page_layout:
            if not isinstance(element, LTTextContainer):
                continue
            # pdfminer's container iteration is untyped; narrow each line explicitly
            for text_line in cast("Iterable[object]", element):
                if not isinstance(text_line, LTTextLine):
                    continue
                glyphs = [glyph for glyph in text_line if isinstance(glyph, LTChar)]
                text = text_line.get_text().strip()
                if not text or not glyphs:
                    continue
                size = round(statistics.median(glyph.size for glyph in glyphs), 1)
                bold = _line_is_bold([glyph.fontname for glyph in glyphs])
                lines.append((text, size, bold, page_number))

    if not lines:
        return [], page_count  # image-only / empty PDF; ingestion turns this into a clear error

    body_size = statistics.mode(size for _, size, _, _ in lines)
    heading_sizes = sorted(
        {size for _, size, _, _ in lines if size >= body_size * HEADING_SIZE_RATIO}, reverse=True
    )
    level_of = {size: index + 1 for index, size in enumerate(heading_sizes)}
    # bold body-size headings sort below every larger-font heading level
    bold_level = min(len(heading_sizes) + 1, MAX_HEADING_LEVEL)

    def level_for(text: str, size: float, bold: bool) -> int | None:
        by_size = level_of.get(size)
        if by_size is not None:
            return by_size
        # promote bold lines only at (or above) body size — a bold line SMALLER
        # than body is a running header / caption / footnote label, which would
        # otherwise be stamped as a heading on every page and shred the trail
        if bold and size >= body_size and _bold_heading_like(text):
            return bold_level
        return None

    blocks = [
        Block(text=text, level=level_for(text, size, bold), page=page)
        for text, size, bold, page in lines
    ]
    return _assemble_sections(blocks, body_separator="\n"), page_count


def _docx_heading_level(style_name: str | None) -> int | None:
    """Map a Word paragraph style to a heading level, or None for body text."""
    if style_name is None:
        return None
    if style_name == "Title":
        return 1
    if style_name.startswith("Heading "):
        try:
            level = int(style_name.removeprefix("Heading "))
        except ValueError:
            return None
        # clamp both ends: a "Heading 0" style would otherwise yield level 0,
        # producing an empty "#" * 0 marker and a malformed heading trail
        return min(max(level, 1), MAX_HEADING_LEVEL)
    return None


def parse_docx(data: bytes) -> tuple[list[Section], None]:
    """Parse a DOCX into sections from its heading styles (no page numbers:
    DOCX is reflowable and stores none)."""
    document = DocxDocument(io.BytesIO(data))
    blocks: list[Block] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = paragraph.style.name if paragraph.style else None
        blocks.append(Block(text=text, level=_docx_heading_level(style_name), page=None))
    return _assemble_sections(blocks), None


def parse_document(
    data: bytes, mime_type: str, max_pages: int | None = None
) -> tuple[list[Section], int | None]:
    """Dispatch to the parser for a mime type; raises for unsupported types.

    `max_pages` caps PDF parsing (raising `PageLimitError`); other formats have
    no page count and ignore it.
    """
    if mime_type == MARKDOWN_MIME:
        return markdown_sections(data.decode("utf-8")), None
    if mime_type == PDF_MIME:
        return parse_pdf(data, max_pages=max_pages)
    if mime_type == DOCX_MIME:
        return parse_docx(data)
    raise UnsupportedMediaTypeError(mime_type)
