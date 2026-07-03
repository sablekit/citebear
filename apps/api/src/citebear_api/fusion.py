"""Reciprocal Rank Fusion (SPEC §5.2).

Rank-based fusion of the vector and keyword result lists: no score-scale
gymnastics between cosine distance and ts_rank, only their positions. Each
item's fused score is the sum over lists of ``1 / (k + rank)`` (rank starting
at 1); higher is better. k=60 is the standard constant — large enough that the
first few ranks are close, so a hit both systems agree on outranks either
system's lone top result.
"""

from collections.abc import Hashable, Sequence

RRF_K = 60


def reciprocal_rank_fusion[T: Hashable](
    rankings: Sequence[Sequence[T]], *, k: int = RRF_K
) -> list[T]:
    """Fuse ranked lists (each best-first) into one deduplicated ranking.

    Ties keep first-seen order, so the result is deterministic.
    """
    scores: dict[T, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: scores[item], reverse=True)
