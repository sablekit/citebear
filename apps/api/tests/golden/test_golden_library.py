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

from citebear_api.db import run_async
from citebear_api.preloaded import LIBRARY
from citebear_api.retrieval import FINAL_TOP_K

from .dataset import GOLDEN_LIBRARY
from .pipeline import require_corpus, top5_contents

pytestmark = pytest.mark.golden_library

_LIBRARY_TITLES = {doc.title for doc in LIBRARY}


@pytest.fixture(scope="module", autouse=True)
def _require_library() -> None:  # pyright: ignore[reportUnusedFunction]
    # skips when the library isn't loaded here, but fails on a partial load —
    # so the manual golden-library job can't go green having asserted nothing
    require_corpus(_LIBRARY_TITLES)


@pytest.mark.parametrize(("question", "expected"), GOLDEN_LIBRARY)
def test_expected_chunk_in_top5(question: str, expected: str) -> None:
    contents = run_async(top5_contents(question))
    assert any(expected in content for content in contents), (
        f"{expected!r} not in top-{FINAL_TOP_K} for {question!r}"
    )
