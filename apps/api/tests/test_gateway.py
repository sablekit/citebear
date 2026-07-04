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
