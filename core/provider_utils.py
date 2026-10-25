"""Provider 请求超时控制。"""

import asyncio
from typing import TYPE_CHECKING, Any

from astrbot.core.log import LogManager

if TYPE_CHECKING:
    from ..main import Mnemosyne

logger = LogManager.GetLogger(__name__)

DEFAULT_EMBEDDING_TIMEOUT_SECONDS = 15
DEFAULT_SUMMARY_TIMEOUT_SECONDS = 60


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
