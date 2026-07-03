from itertools import pairwise

import tiktoken

from citebear_api.chunking import (
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    chunk_markdown,
)

# the splitter sizes pieces by summing per-split token counts; re-encoding
# the joined text can differ by a token or two at BPE boundaries, so the
# ~400 target (SPEC §5.1) carries a small tolerance
MAX_TOKENS = int(TARGET_TOKENS * 1.05)


def _long_paragraphs(sentences: int) -> str:
    return " ".join(
        f"Sentence number {i} talks about retrieval pipelines and vector search quality."
        for i in range(sentences)
    )


def test_empty_document_yields_no_chunks() -> None:
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  ") == []


def test_short_sections_stay_whole() -> None:
    text = "# Install\n\nRun the installer.\n\n# Configure\n\nEdit the config file."
    chunks = chunk_markdown(text)
    assert len(chunks) == 2
    assert "Run the installer." in chunks[0].content
    assert "Edit the config file." in chunks[1].content


def test_section_path_reflects_heading_trail() -> None:
    text = "# Install\n\n## Linux\n\n### Debian\n\nUse apt to install the package."
    chunks = chunk_markdown(text)
    assert chunks[-1].section_path == ["Install", "Linux", "Debian"]


def test_heading_line_is_preserved_in_content() -> None:
    text = "# Install\n\nRun the installer."
    chunks = chunk_markdown(text)
    assert "# Install" in chunks[0].content


def test_preamble_before_first_heading_has_empty_path() -> None:
    text = "Intro paragraph before any heading.\n\n# First\n\nBody."
    chunks = chunk_markdown(text)
    assert chunks[0].section_path == []
    assert "Intro paragraph" in chunks[0].content


def test_oversized_section_splits_under_target() -> None:
    text = f"# Big\n\n{_long_paragraphs(120)}"
    chunks = chunk_markdown(text)
    assert len(chunks) > 1
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    # all pieces of the split section keep the section's heading trail
    assert all(c.section_path == ["Big"] for c in chunks)


def test_oversized_section_split_has_overlap() -> None:
    text = f"# Big\n\n{_long_paragraphs(120)}"
    chunks = chunk_markdown(text)
    assert len(chunks) > 1
    # consecutive chunks share content: the tail of one reappears in the next
    for prev, nxt in pairwise(chunks):
        tail = prev.content[-40:]
        assert tail in nxt.content or OVERLAP_TOKENS == 0


def test_chunks_never_cross_heading_boundary() -> None:
    text = f"# Alpha\n\n{_long_paragraphs(120)}\n\n# Omega\n\nUnique omega marker sentence."
    chunks = chunk_markdown(text)
    for chunk in chunks:
        crosses = "Sentence number" in chunk.content and "omega marker" in chunk.content
        assert not crosses


def test_oversized_heading_does_not_crash_the_splitter() -> None:
    monster_heading = "# " + " ".join(f"word{i}" for i in range(500))
    text = f"{monster_heading}\n\n{_long_paragraphs(120)}"
    chunks = chunk_markdown(text)
    assert len(chunks) > 1
    assert all(c.token_count <= MAX_TOKENS for c in chunks)


def test_ordinals_are_sequential_from_zero() -> None:
    text = f"# A\n\n{_long_paragraphs(120)}\n\n# B\n\nShort."
    chunks = chunk_markdown(text)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_token_count_matches_encoder() -> None:
    text = "# A\n\nSome plain content."
    chunks = chunk_markdown(text)
    encoding = tiktoken.get_encoding("cl100k_base")
    assert chunks[0].token_count == len(encoding.encode(chunks[0].content))


def test_markdown_chunks_have_no_pages() -> None:
    chunks = chunk_markdown("# A\n\nBody.")
    assert chunks[0].page_start is None
    assert chunks[0].page_end is None


def test_first_piece_embeds_its_own_content() -> None:
    # a short section is a single (first) piece: embed_text == content, no trail
    chunks = chunk_markdown("# Install\n\nRun the installer.")
    assert chunks[0].embed_text == chunks[0].content


def test_continuation_pieces_embed_the_section_trail() -> None:
    text = f"# Install\n\n## Linux\n\n{_long_paragraphs(120)}"
    chunks = chunk_markdown(text)
    assert len(chunks) > 1
    trail = "Install > Linux"
    # first piece keeps its heading; embed_text is just its content
    assert chunks[0].embed_text == chunks[0].content
    # continuation pieces prepend the trail for embedding, content unchanged
    for chunk in chunks[1:]:
        assert chunk.embed_text == f"{trail}\n\n{chunk.content}"
        assert not chunk.content.startswith(trail)


def test_continuation_without_heading_has_no_trail() -> None:
    # preamble before any heading -> empty section_path -> no trail even on splits
    chunks = chunk_markdown(_long_paragraphs(120))
    assert len(chunks) > 1
    assert all(chunk.embed_text == chunk.content for chunk in chunks)
