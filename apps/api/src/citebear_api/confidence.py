"""Confidence and the refusal threshold, from rerank scores (SPEC §5.3).

The best rerank score across the final chunks decides both whether to answer at
all and how confident the answer is:

- best score >= 7 -> high confidence
- retrieved but weaker -> low confidence (the UI shows a badge)
- nothing above 4 -> refuse *without* calling the generator (saves a model call
  and removes any chance to fabricate)
"""

from citebear_api.retrieval import RetrievedChunk

HIGH_SCORE = 7.0
REFUSAL_SCORE = 4.0

HIGH = "high"
LOW = "low"


def assess(chunks: list[RetrievedChunk]) -> tuple[str, bool]:
    """Return ``(confidence, should_generate)`` for the reranked chunks."""
    best = max((chunk.score for chunk in chunks), default=0.0)
    if best <= REFUSAL_SCORE:
        return LOW, False
    return (HIGH if best >= HIGH_SCORE else LOW), True
