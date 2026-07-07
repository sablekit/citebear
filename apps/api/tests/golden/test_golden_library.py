"""Golden retrieval over the preloaded library (SPEC §9 / §11).

Same real hybrid + rerank pipeline as the self-owned golden set, but over the
preloaded library (Calibre / Debian / NIST) — real third-party content the
reranker must still surface. Marked ``golden_library`` so it is excluded from
the every-push run and opted into by the golden workflow's manual library job
with ``-m golden_library``.

Gated on the library being ingested (``python -m citebear_api.load_library``):
it skips cleanly against a DB that only has the self-owned corpus, so a PR-gate
run over the Markdown corpus never trips it.
"""

import pytest
from sqlalchemy import select

from citebear_api.db import get_session_factory, run_async
from citebear_api.models import Document
from citebear_api.preloaded import LIBRARY
from citebear_api.retrieval import FINAL_TOP_K

from .dataset import GOLDEN_LIBRARY
from .pipeline import top5_contents

pytestmark = pytest.mark.golden_library

_LIBRARY_TITLES = {doc.title for doc in LIBRARY}


async def _ready_titles() -> set[str]:
    async with get_session_factory()() as db:
        titles = (
            await db.execute(select(Document.title).where(Document.status == "ready"))
        ).scalars()
        return set(titles)


@pytest.fixture(scope="module", autouse=True)
def _require_library() -> None:  # pyright: ignore[reportUnusedFunction]
    try:
        titles = run_async(_ready_titles())
    except Exception as exc:  # DB unreachable / not migrated
        pytest.skip(f"golden library set needs a live database: {exc}")
    missing = _LIBRARY_TITLES - titles
    if missing:
        pytest.skip(f"golden library set needs the library ingested (missing: {sorted(missing)})")


@pytest.mark.parametrize(("question", "expected"), GOLDEN_LIBRARY)
def test_expected_chunk_in_top5(question: str, expected: str) -> None:
    contents = run_async(top5_contents(question))
    assert any(expected in content for content in contents), (
        f"{expected!r} not in top-{FINAL_TOP_K} for {question!r}"
    )
