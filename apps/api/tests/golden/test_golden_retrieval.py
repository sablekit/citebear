"""Golden retrieval set (SPEC §9).

Runs the real hybrid + rerank pipeline against a live DB + gateway and asserts
each question surfaces its expected chunk in the reranked top-5. Marked
``golden`` so it is excluded from the every-push run (pyproject addopts) and
opted into by the golden workflow with ``-m golden``.

Prerequisite: the self-owned corpus is ingested (the workflow does this; locally
run ``python -m citebear_api.ingest`` for SPEC.md / README.md / AGENTS.md). The
module skips cleanly if the DB is unreachable or empty.
"""

import pytest
from sqlalchemy import func, select

from citebear_api.db import get_session_factory, run_async
from citebear_api.models import Chunk
from citebear_api.retrieval import FINAL_TOP_K

from .dataset import GOLDEN
from .pipeline import top5_contents

pytestmark = pytest.mark.golden


async def _chunk_count() -> int:
    async with get_session_factory()() as db:
        return (await db.execute(select(func.count()).select_from(Chunk))).scalar_one()


@pytest.fixture(scope="module", autouse=True)
def _require_ingested_corpus() -> None:  # pyright: ignore[reportUnusedFunction]
    try:
        count = run_async(_chunk_count())
    except Exception as exc:  # DB unreachable / not migrated
        pytest.skip(f"golden set needs a live database: {exc}")
    if count == 0:
        pytest.skip("golden set needs the corpus ingested (run citebear_api.ingest)")


@pytest.mark.parametrize(("question", "expected"), GOLDEN)
def test_expected_chunk_in_top5(question: str, expected: str) -> None:
    contents = run_async(top5_contents(question))
    assert any(expected in content for content in contents), (
        f"{expected!r} not in top-{FINAL_TOP_K} for {question!r}"
    )
