"""Citation assembly and the post-check (SPEC §5.3, §5.4).

`build_citations` turns the retrieved chunks into the candidate list for the
sources event, numbered exactly as the generator sees them (marker = position).
It is sent before generation, so the UI has metadata for any marker the answer
goes on to use.

`cited_markers` runs after streaming: it keeps only the markers the answer
actually used *and* that map to a real chunk — hallucinated or out-of-range
markers are dropped, so only genuine citations reach `message_citations`.
"""

import re

from citebear_api.events import Citation
from citebear_api.retrieval import RetrievedChunk

_MARKER = re.compile(r"\[(\d+)\]")


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            marker=i + 1,
            chunk_id=chunk.chunk_id,
            doc_title=chunk.document_title,
            page=chunk.page_start,
            section_path=chunk.section_path,
            source_url=chunk.source_url,
            snippet=chunk.content,
        )
        for i, chunk in enumerate(chunks)
    ]


def cited_markers(answer: str, chunk_count: int) -> list[int]:
    """Valid markers used in the answer, in first-appearance order, deduplicated."""
    seen: list[int] = []
    for match in _MARKER.finditer(answer):
        marker = int(match.group(1))
        if 1 <= marker <= chunk_count and marker not in seen:
            seen.append(marker)
    return seen
