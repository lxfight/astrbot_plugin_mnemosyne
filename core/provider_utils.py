"""Provider 请求超时控制。"""

import asyncio
from typing import TYPE_CHECKING, Any

from astrbot.api import logger

if TYPE_CHECKING:
    from ..main import Mnemosyne

DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 15
DEFAULT_SUMMARY_TIMEOUT_SECONDS = 60
EMBEDDING_BATCH_SIZE = 16


async def request_embedding(
    plugin: "Mnemosyne", text: str
) -> list[float] | None:
    timeout = plugin.config.get(
        "embedding_request_timeout_seconds", DEFAULT_EMBEDDING_TIMEOUT_SECONDS
    )
    try:
        return await asyncio.wait_for(
            plugin.embedding_provider.get_embedding(text),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.error(f"Embedding 请求超时（{timeout} 秒），已取消。")
        raise


async def request_embeddings(
    plugin: "Mnemosyne", texts: list[str]
) -> list[list[float]]:
    """按批次获取文本向量，并在 Provider 不支持批量接口时回退到单条请求。"""
    if not texts:
        return []

    provider = plugin.embedding_provider
    timeout = plugin.config.get(
        "embedding_request_timeout_seconds", DEFAULT_EMBEDDING_TIMEOUT_SECONDS
    )
    native_batch = getattr(provider, "get_embeddings_batch", None)
    if callable(native_batch):
        batch_count = (len(texts) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
        try:
            embeddings = await asyncio.wait_for(
                native_batch(texts, batch_size=EMBEDDING_BATCH_SIZE),
                timeout=timeout * batch_count,
            )
        except asyncio.TimeoutError:
            logger.error(f"Embedding 批量请求超时（{timeout} 秒/批），已取消。")
            raise

        if len(embeddings) != len(texts) or any(not item for item in embeddings):
            raise RuntimeError("Embedding Provider 返回的向量数量或内容无效")
        return embeddings

    batch_embed = getattr(provider, "get_embeddings", None)
    if not callable(batch_embed):
        batch_embed = getattr(provider, "embed_texts", None)

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch_texts = texts[start : start + EMBEDDING_BATCH_SIZE]
        try:
            if callable(batch_embed):
                batch_embeddings = await asyncio.wait_for(
                    batch_embed(batch_texts),
                    timeout=timeout,
                )
            else:
                batch_embeddings = [
                    await request_embedding(plugin, text) for text in batch_texts
                ]
        except asyncio.TimeoutError:
            logger.error(f"Embedding 批量请求超时（{timeout} 秒），已取消。")
            raise

        if len(batch_embeddings) != len(batch_texts) or any(
            not embedding for embedding in batch_embeddings
        ):
            raise RuntimeError("Embedding Provider 返回的向量数量或内容无效")
        embeddings.extend(batch_embeddings)

    return embeddings


async def request_summary_completion(
    plugin: "Mnemosyne",
    provider: Any,
    *,
    provider_label: str,
    prompt: str,
    contexts: list[dict[str, Any]],
    **kwargs: Any,
) -> Any:
    timeout = plugin.config.get(
        "summary_request_timeout_seconds", DEFAULT_SUMMARY_TIMEOUT_SECONDS
    )
    try:
        return await asyncio.wait_for(
            provider.text_chat(prompt=prompt, contexts=contexts, **kwargs),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.error(
            f"{provider_label}总结 Provider 请求超时（{timeout} 秒），已取消。"
        )
        raise
