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

from citebear_api.db import run_async
from citebear_api.retrieval import FINAL_TOP_K

from .dataset import GOLDEN
from .pipeline import require_corpus, top5_contents

pytestmark = pytest.mark.golden

# The self-owned corpus the workflow ingests. Gating on these titles (not a raw
# chunk count) keeps the set from hard-failing when a *different* corpus shares
# the DB — a count-based gate would see chunks and wrongly run the self-owned
# pairs against, say, a library-only database.
_SELF_OWNED_TITLES = {
    "CiteBear Specification",
    "CiteBear README",
    "CiteBear Agent & Contributor Context",
}


@pytest.fixture(scope="module", autouse=True)
def _require_ingested_corpus() -> None:  # pyright: ignore[reportUnusedFunction]
    require_corpus(_SELF_OWNED_TITLES)


@pytest.mark.parametrize(("question", "expected"), GOLDEN)
def test_expected_chunk_in_top5(question: str, expected: str) -> None:
    contents = run_async(top5_contents(question))
    assert any(expected in content for content in contents), (
        f"{expected!r} not in top-{FINAL_TOP_K} for {question!r}"
    )
