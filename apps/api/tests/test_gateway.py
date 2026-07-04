"""Gateway batching: embed_texts splits into batches and preserves input order.

These run without a real gateway by faking the embeddings client — the concern
under test is the batching/ordering logic, not the model call.
"""

import asyncio

import pytest

from citebear_api import gateway


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batch_sizes.append(len(texts))
        # encode each text's integer value as its vector so order is checkable
        return [[float(int(text))] for text in texts]


def test_embed_texts_preserves_order_across_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeEmbeddings()
    monkeypatch.setattr(gateway, "get_embeddings", lambda: fake)
    monkeypatch.setattr(gateway, "EMBED_BATCH_SIZE", 2)

    vectors = asyncio.run(gateway.embed_texts([str(i) for i in range(5)]))

    assert [vector[0] for vector in vectors] == [0.0, 1.0, 2.0, 3.0, 4.0]
    # 5 texts at batch size 2 -> batches of 2, 2, 1 (order of completion may vary)
    assert sorted(fake.batch_sizes) == [1, 2, 2]


def test_embed_texts_empty_returns_empty() -> None:
    assert asyncio.run(gateway.embed_texts([])) == []


def test_with_retry_recovers_from_transient_faults() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("gateway said 429 rate limit")  # transient by message
        return "ok"

    result = asyncio.run(gateway.with_retry(flaky, base_delay=0.0))
    assert result == "ok"
    assert calls == 3


def test_with_retry_does_not_retry_non_transient_errors() -> None:
    calls = 0

    async def boom() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("bad request")  # not transient -> propagate immediately

    with pytest.raises(ValueError, match="bad request"):
        asyncio.run(gateway.with_retry(boom, base_delay=0.0))
    assert calls == 1
