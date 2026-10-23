from __future__ import annotations

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from core import memory_operations


class _ToolEvent:
    unified_msg_origin = "test:FriendMessage:user-1"

    def __init__(self) -> None:
        self._extra: dict[str, object] = {}

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)

    def set_extra(self, key, value) -> None:
        self._extra[key] = value


class TestMemoryTool(IsolatedAsyncioTestCase):
    async def test_store_memory_from_tool_uses_current_event(self) -> None:
        plugin = SimpleNamespace(config={"max_prompt_chars_for_embedding": 4000})
        event = _ToolEvent()
        store = AsyncMock(return_value=True)

        with patch.object(memory_operations, "store_manual_memory", store):
            message = await memory_operations.store_memory_from_tool(
                plugin, event, "  Alice likes tea.  "
            )

        store.assert_awaited_once_with(
            plugin=plugin,
            event=event,
            memory_content="Alice likes tea.",
            source="llm_tool",
        )
        self.assertEqual(
            event._extra[memory_operations.CAPTURED_MEMORY_CONTENT_EXTRA_KEY],
            "Alice likes tea.",
        )
        self.assertIn("已写入", message)

    async def test_store_memory_from_tool_skips_explicit_capture_duplicate(
        self,
    ) -> None:
        plugin = SimpleNamespace(config={"max_prompt_chars_for_embedding": 4000})
        event = _ToolEvent()
        event.set_extra(
            memory_operations.CAPTURED_MEMORY_CONTENT_EXTRA_KEY,
            "Alice likes tea.",
        )
        store = AsyncMock(return_value=True)

        with patch.object(memory_operations, "store_manual_memory", store):
            message = await memory_operations.store_memory_from_tool(
                plugin, event, "Alice likes tea."
            )

        store.assert_not_awaited()
        self.assertIn("无需重复", message)

    async def test_store_memory_from_tool_rejects_empty_content(self) -> None:
        plugin = SimpleNamespace(config={"max_prompt_chars_for_embedding": 4000})
        event = _ToolEvent()
        store = AsyncMock(return_value=True)

        with patch.object(memory_operations, "store_manual_memory", store):
            message = await memory_operations.store_memory_from_tool(
                plugin, event, "   "
            )

        store.assert_not_awaited()
        self.assertIn("为空", message)
