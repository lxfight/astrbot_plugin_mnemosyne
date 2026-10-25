import asyncio
from types import SimpleNamespace

import pytest

from core.provider_utils import request_embedding


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
