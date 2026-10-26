import asyncio
from types import SimpleNamespace

import pytest

from core.provider_utils import (
    EMBEDDING_BATCH_SIZE,
    request_embedding,
    request_embeddings,
)


class _HangingEmbeddingProvider:
    def __init__(self):
        self.cancelled = False

    async def get_embedding(self, _text):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest.mark.asyncio
async def test_request_embedding_cancels_after_timeout():
    provider = _HangingEmbeddingProvider()
    plugin = SimpleNamespace(
        embedding_provider=provider,
        config={"embedding_request_timeout_seconds": 0.01},
    )

    with pytest.raises(asyncio.TimeoutError):
        await request_embedding(plugin, "hello")

    assert provider.cancelled is True


class _BatchEmbeddingProvider:
    def __init__(self):
        self.batch_calls = []

    async def get_embedding(self, _text):
        raise AssertionError("batch provider should not use single requests")

    async def get_embeddings(self, texts):
        self.batch_calls.append(texts)
        return [[float(len(text)), 0.5] for text in texts]


class _HangingBatchEmbeddingProvider:
    def __init__(self):
        self.cancelled = False

    async def get_embeddings(self, _texts):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _NativeBatchEmbeddingProvider:
    def __init__(self):
        self.batch_calls = []

    async def get_embedding(self, _text):
        raise AssertionError("native batch provider should not use single requests")

    async def get_embeddings_batch(self, texts, **kwargs):
        self.batch_calls.append((texts, kwargs))
        return [[float(len(text)), 0.5] for text in texts]


class _HangingNativeBatchEmbeddingProvider:
    def __init__(self):
        self.cancelled = False

    async def get_embeddings_batch(self, _texts, **_kwargs):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest.mark.asyncio
async def test_request_embeddings_uses_batches_and_preserves_order():
    provider = _BatchEmbeddingProvider()
    plugin = SimpleNamespace(
        embedding_provider=provider,
        config={"embedding_request_timeout_seconds": 1},
    )
    texts = [f"text-{index}" for index in range(EMBEDDING_BATCH_SIZE + 1)]

    embeddings = await request_embeddings(plugin, texts)

    assert [len(call) for call in provider.batch_calls] == [16, 1]
    assert embeddings == [[float(len(text)), 0.5] for text in texts]


@pytest.mark.asyncio
async def test_request_embeddings_prefers_provider_native_batch_api():
    provider = _NativeBatchEmbeddingProvider()
    plugin = SimpleNamespace(
        embedding_provider=provider,
        config={"embedding_request_timeout_seconds": 1},
    )
    texts = [f"text-{index}" for index in range(EMBEDDING_BATCH_SIZE + 1)]

    embeddings = await request_embeddings(plugin, texts)

    assert len(provider.batch_calls) == 1
    batch_texts, kwargs = provider.batch_calls[0]
    assert batch_texts == texts
    assert kwargs["batch_size"] == EMBEDDING_BATCH_SIZE
    assert embeddings == [[float(len(text)), 0.5] for text in texts]


@pytest.mark.asyncio
async def test_request_embeddings_cancels_batch_after_timeout():
    provider = _HangingBatchEmbeddingProvider()
    plugin = SimpleNamespace(
        embedding_provider=provider,
        config={"embedding_request_timeout_seconds": 0.01},
    )

    with pytest.raises(asyncio.TimeoutError):
        await request_embeddings(plugin, ["hello"])

    assert provider.cancelled is True


@pytest.mark.asyncio
async def test_request_embeddings_cancels_native_batch_after_timeout():
    provider = _HangingNativeBatchEmbeddingProvider()
    plugin = SimpleNamespace(
        embedding_provider=provider,
        config={"embedding_request_timeout_seconds": 0.01},
    )

    with pytest.raises(asyncio.TimeoutError):
        await request_embeddings(plugin, ["hello"])

    assert provider.cancelled is True


class _SingleEmbeddingProvider:
    def __init__(self):
        self.calls = []

    async def get_embedding(self, text):
        self.calls.append(text)
        return [float(len(text)), 0.5]


@pytest.mark.asyncio
async def test_request_embeddings_falls_back_to_single_requests():
    provider = _SingleEmbeddingProvider()
    plugin = SimpleNamespace(embedding_provider=provider, config={})

    embeddings = await request_embeddings(plugin, ["one", "three"])

    assert provider.calls == ["one", "three"]
    assert embeddings == [[3.0, 0.5], [5.0, 0.5]]
