"""Reciprocal Rank Fusion (SPEC §5.2, §9 unit target).

RRF merges the vector and keyword rankings by position only, so these tests pin
the rank-discounting math and the tie/dedup behaviour without any DB or model.
"""

from citebear_api.fusion import reciprocal_rank_fusion


def test_single_list_preserves_order() -> None:
    assert reciprocal_rank_fusion([["a", "b", "c"]]) == ["a", "b", "c"]


def test_dedup_across_lists() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
    assert sorted(fused) == ["a", "b"]
    assert len(fused) == 2


def test_agreement_beats_a_single_top_hit() -> None:
    # "b" is rank 2 in both lists; its summed score beats items that are rank 1
    # in only one list — the point of rank fusion.
    fused = reciprocal_rank_fusion([["a", "b"], ["c", "b"]])
    assert fused[0] == "b"


def test_full_order_is_deterministic() -> None:
    # k=60: b=1/62+1/61, c=1/63+1/62, a=1/61, d=1/63 -> b > c > a > d
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "d"]])
    assert fused == ["b", "c", "a", "d"]


def test_ties_keep_first_seen_order() -> None:
    # a and c are both rank 1 in one list only -> equal score -> first-seen wins
    fused = reciprocal_rank_fusion([["a"], ["c"]])
    assert fused == ["a", "c"]


def test_empty_input() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
