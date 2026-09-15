from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


def _ensure_dependency_stubs() -> None:
    if "astrbot" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api_event = types.ModuleType("astrbot.api.event")
        astrbot_api_provider = types.ModuleType("astrbot.api.provider")
        astrbot_api_star = types.ModuleType("astrbot.api.star")
        astrbot_core = types.ModuleType("astrbot.core")
        astrbot_core_agent = types.ModuleType("astrbot.core.agent")
        astrbot_core_agent_message = types.ModuleType("astrbot.core.agent.message")
        astrbot_core_log = types.ModuleType("astrbot.core.log")

        class _Logger:
            def debug(self, *_args, **_kwargs):
                return None

            def info(self, *_args, **_kwargs):
                return None

            def warning(self, *_args, **_kwargs):
                return None

            def error(self, *_args, **_kwargs):
                return None

        class _LogManager:
            @staticmethod
            def GetLogger(*_args, **_kwargs):
                return _Logger()

        class _AstrMessageEvent:
            pass

        class _ProviderRequest:
            pass

        class _LLMResponse:
            pass

        class _StarTools:
            @staticmethod
            def get_data_dir():
                return PLUGIN_ROOT / ".test-data"

        class _TextPart:
            def __init__(self, text):
                self.text = text
                self._no_save = False

            def mark_as_temp(self):
                self._no_save = True
                return self

        astrbot_api.logger = _Logger()
        astrbot_api_event.AstrMessageEvent = _AstrMessageEvent
        astrbot_api_provider.ProviderRequest = _ProviderRequest
        astrbot_api_provider.LLMResponse = _LLMResponse
        astrbot_api_star.StarTools = _StarTools
        astrbot_core_agent_message.TextPart = _TextPart
        astrbot_core_log.LogManager = _LogManager

        astrbot.api = astrbot_api
        astrbot.core = astrbot_core
        astrbot_api.star = astrbot_api_star
        astrbot_core.agent = astrbot_core_agent
        astrbot_core_agent.message = astrbot_core_agent_message
        astrbot_core.log = astrbot_core_log

        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
        sys.modules["astrbot.api.event"] = astrbot_api_event
        sys.modules["astrbot.api.provider"] = astrbot_api_provider
        sys.modules["astrbot.api.star"] = astrbot_api_star
        sys.modules["astrbot.core"] = astrbot_core
        sys.modules["astrbot.core.agent"] = astrbot_core_agent
        sys.modules["astrbot.core.agent.message"] = astrbot_core_agent_message
        sys.modules["astrbot.core.log"] = astrbot_core_log

    if "astrbot.core.agent.message" not in sys.modules:
        astrbot_core = sys.modules.setdefault(
            "astrbot.core", types.ModuleType("astrbot.core")
        )
        astrbot_core_agent = sys.modules.setdefault(
            "astrbot.core.agent", types.ModuleType("astrbot.core.agent")
        )
        astrbot_core_agent_message = types.ModuleType("astrbot.core.agent.message")

        class _TextPart:
            def __init__(self, text):
                self.text = text
                self._no_save = False

            def mark_as_temp(self):
                self._no_save = True
                return self

        astrbot_core_agent_message.TextPart = _TextPart
        astrbot_core.agent = astrbot_core_agent
        astrbot_core_agent.message = astrbot_core_agent_message
        sys.modules["astrbot.core.agent.message"] = astrbot_core_agent_message


_ensure_dependency_stubs()

import core.memory_operations as memory_operations  # noqa: E402
from core.memory_operations import (  # noqa: E402
    _build_identity_prefixed_user_text,
    _build_lightweight_graph_metadata,
    _build_turn_marker,
    _get_last_user_turn_store,
    _get_event_extra,
    _mark_turn_once,
    _post_process_search_results,
    _remember_last_user_turn,
    _resolve_sender_identity,
)
from memory_manager.context_manager import ConversationContextManager  # noqa: E402
from memory_manager.message_counter import MessageCounter  # noqa: E402
from core.tools import (  # noqa: E402
    extract_query_keywords,
    format_context_to_string,
    format_tool_calls_result_to_string,
    pack_memory_content,
    remove_mnemosyne_tags,
    resolve_max_prompt_chars,
    split_memory_content_meta,
    strip_memory_meta,
    truncate_for_embedding,
)


class _Plugin:
    def __init__(self, config: dict):
        self.config = config


class _ToolFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _ToolFunction(name, arguments)

    def model_dump(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


class _ToolCallsInfo:
    role = "assistant"
    content = None

    def __init__(self, tool_calls):
        self.tool_calls = tool_calls

    def model_dump(self):
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in self.tool_calls
            ],
        }


class _ToolResultMsg:
    role = "tool"

    def __init__(self, call_id, content):
        self.tool_call_id = call_id
        self.content = content

    def model_dump(self):
        return {
            "role": self.role,
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


class _ToolCallsResult:
    def __init__(self, info, results):
        self.tool_calls_info = info
        self.tool_calls_result = results


class _SingleArgExtraEvent:
    def __init__(self, values):
        self.values = values

    def get_extra(self, key):
        return self.values.get(key)


class _ProviderRequestForMemory:
    def __init__(self, prompt):
        self.prompt = prompt
        self.contexts = []
        self.system_prompt = ""
        self.image_urls = []


class _EventWithExtra:
    unified_msg_origin = "test:FriendMessage:u1"
    image_urls = []

    def __init__(self):
        self._extra = {}
        self.message_obj = _TurnMessageObj("msg-explicit-1")

    def get_sender_id(self):
        return "u1"

    def get_message_outline(self):
        return "记住: Alice likes tea"

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)

    def set_extra(self, key, value):
        self._extra[key] = value


class _ConnectedVectorDB:
    def is_connected(self):
        return True


class _Counter:
    def __init__(self):
        self.counts = {}

    def increment_counter(self, session_id):
        self.counts[session_id] = self.counts.get(session_id, 0) + 1

    def get_counter(self, session_id):
        return self.counts.get(session_id, 0)


class _ConversationManager:
    async def get_curr_conversation_id(self, _umo):
        return "conv-1"

    async def get_conversation(self, _umo, _conversation_id):
        return types.SimpleNamespace(persona_id="persona-1")


class _Context:
    conversation_manager = _ConversationManager()


class _MemoryPlugin:
    def __init__(self):
        self.config = {
            "enable_explicit_memory_capture": True,
            "memory_injection_interval": 2,
            "vector_db_type": "chroma",
        }
        self.vector_db = _ConnectedVectorDB()
        self.embedding_provider = object()
        self._embedding_provider_ready = True
        self.context_manager = ConversationContextManager()
        self.msg_counter = _Counter()
        self.context = _Context()
        self.collection_name = "default"
        self._injection_round_counter = {}
        self._injection_round_counter_updated_at = {}


class _TurnMessageObj:
    def __init__(self, message_id):
        self.message_id = message_id


class _TurnEvent:
    unified_msg_origin = "test:FriendMessage:u1"

    def __init__(self, message_id, outline="hello"):
        self.message_obj = _TurnMessageObj(message_id)
        self.outline = outline

    def get_sender_id(self):
        return "u1"

    def get_message_outline(self):
        return self.outline


_UNSET = object()


class _AssistantResponse:
    role = "assistant"

    def __init__(self, completion_text, tools_call_name=_UNSET):
        self.completion_text = completion_text
        if tools_call_name is not _UNSET:
            self.tools_call_name = tools_call_name


class TestMemoryMetaHelpers(unittest.TestCase):
    def test_pack_split_strip_round_trip(self) -> None:
        content = "Alice met Bob"
        metadata = {"participants": ["u1"], "relations": [["alice", "bob"]]}

        packed = pack_memory_content(content, metadata)
        pure_content, parsed_meta = split_memory_content_meta(packed)

        self.assertEqual(pure_content, content)
        self.assertEqual(parsed_meta, metadata)
        self.assertEqual(strip_memory_meta(packed), content)

    def test_extract_query_keywords_supports_mixed_language(self) -> None:
        text = "Alpha_1 与 项目X 在 北京 协作"
        keywords = extract_query_keywords(text, min_token_len=2)

        self.assertIn("alpha_1", keywords)
        self.assertIn("项目", keywords)
        self.assertIn("北京", keywords)

    def test_resolve_max_prompt_chars_uses_config_and_fallback(self) -> None:
        self.assertEqual(
            resolve_max_prompt_chars({"max_prompt_chars_for_embedding": "512"}), 512
        )
        self.assertEqual(
            resolve_max_prompt_chars({"max_prompt_chars_for_embedding": 0}), 4000
        )
        self.assertEqual(resolve_max_prompt_chars(None), 4000)

    def test_truncate_for_embedding_supports_optional_suffix(self) -> None:
        text = "x" * 20
        plain, plain_changed = truncate_for_embedding(text, 8, append_suffix=False)
        suffixed, suffixed_changed = truncate_for_embedding(text, 8, append_suffix=True)

        self.assertTrue(plain_changed)
        self.assertEqual(plain, "x" * 8)
        self.assertTrue(suffixed_changed)
        self.assertEqual(suffixed, "x" * 8 + "…(truncated)")


class TestConfigSchema(unittest.TestCase):
    def test_memory_injection_schema_has_single_interval_gate(self) -> None:
        duplicates: list[str] = []

        def object_pairs_hook(pairs):
            seen = set()
            for key, _value in pairs:
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
            return dict(pairs)

        schema_text = (PLUGIN_ROOT / "_conf_schema.json").read_text(encoding="utf-8")
        schema = json.loads(schema_text, object_pairs_hook=object_pairs_hook)

        self.assertNotIn("memory_injection_interval", duplicates)
        interval_schema = schema["memory_injection_interval"]
        self.assertEqual(interval_schema["default"], 1)
        self.assertEqual(interval_schema["minimum"], 1)
        self.assertEqual(interval_schema["maximum"], 50)
        self.assertIn("extra_user_parts", schema["memory_injection_method"]["options"])
        self.assertFalse(schema["include_tool_context_in_summary"]["default"])


class TestHandleQueryMemory(unittest.IsolatedAsyncioTestCase):
    def test_injection_interval_falls_back_for_invalid_values(self) -> None:
        for raw_value in ("bad", 0, -3, None):
            plugin = _Plugin({"memory_injection_interval": raw_value})

            self.assertEqual(
                memory_operations._resolve_memory_injection_interval(plugin), 1
            )

    async def test_explicit_memory_capture_runs_before_interval_gate(self) -> None:
        plugin = _MemoryPlugin()
        event = _EventWithExtra()
        req = _ProviderRequestForMemory("记住: Alice likes tea")
        stored_calls: list[dict] = []

        async def fake_store_manual_memory(**kwargs):
            stored_calls.append(kwargs)
            return True

        original_store_manual_memory = memory_operations.store_manual_memory
        memory_operations.store_manual_memory = fake_store_manual_memory
        try:
            await memory_operations.handle_query_memory(plugin, event, req)
        finally:
            memory_operations.store_manual_memory = original_store_manual_memory

        self.assertEqual(len(stored_calls), 1)
        self.assertEqual(stored_calls[0]["memory_content"], "Alice likes tea")
        self.assertEqual(stored_calls[0]["source"], "explicit_trigger")
        self.assertEqual(plugin._injection_round_counter[event.unified_msg_origin], 1)
        self.assertEqual(plugin.msg_counter.get_counter(event.unified_msg_origin), 1)
        self.assertEqual(req.prompt, "记住: Alice likes tea")


class TestHandleLlmResponse(unittest.IsolatedAsyncioTestCase):
    async def test_response_marker_does_not_fallback_to_previous_turn(self) -> None:
        plugin = _MemoryPlugin()
        session_id = "test:FriendMessage:u1"
        first_event = _TurnEvent("msg-1")
        first_marker = _build_turn_marker(plugin, first_event, session_id=session_id)
        plugin.context_manager.add_message(session_id, "user", "first user")
        plugin.context_manager.add_message(session_id, "assistant", "first assistant")
        plugin.msg_counter.increment_counter(session_id)
        plugin.msg_counter.increment_counter(session_id)
        _mark_turn_once(plugin, "_mnemosyne_recorded_user_turns", first_marker)
        _mark_turn_once(plugin, "_mnemosyne_recorded_assistant_turns", first_marker)
        _remember_last_user_turn(plugin, session_id, first_marker)

        summary_calls: list[tuple] = []

        async def fake_check_and_trigger_summary(*args):
            summary_calls.append(args)

        original_check = memory_operations._check_and_trigger_summary
        memory_operations._check_and_trigger_summary = fake_check_and_trigger_summary
        try:
            await memory_operations.handle_on_llm_resp(
                plugin, _TurnEvent("msg-2"), _AssistantResponse("second assistant")
            )
        finally:
            memory_operations._check_and_trigger_summary = original_check

        history = plugin.context_manager.get_history(session_id)
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])
        self.assertEqual([item["content"] for item in history], ["first user", "first assistant"])
        self.assertEqual(plugin.msg_counter.get_counter(session_id), 2)
        self.assertEqual(len(summary_calls), 1)

    async def test_tools_call_name_none_is_treated_as_no_tool_call(self) -> None:
        plugin = _MemoryPlugin()
        session_id = "test:FriendMessage:u1"
        event = _TurnEvent("msg-none-tools")
        marker = _build_turn_marker(plugin, event, session_id=session_id)
        plugin.context_manager.add_message(session_id, "user", "current user")
        plugin.msg_counter.increment_counter(session_id)
        _mark_turn_once(plugin, "_mnemosyne_recorded_user_turns", marker)
        _remember_last_user_turn(plugin, session_id, marker)

        summary_calls: list[tuple] = []

        async def fake_check_and_trigger_summary(*args):
            summary_calls.append(args)

        original_check = memory_operations._check_and_trigger_summary
        memory_operations._check_and_trigger_summary = fake_check_and_trigger_summary
        try:
            await memory_operations.handle_on_llm_resp(
                plugin,
                event,
                _AssistantResponse("assistant should persist", tools_call_name=None),
            )
        finally:
            memory_operations._check_and_trigger_summary = original_check

        history = plugin.context_manager.get_history(session_id)
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertEqual(history[-1]["content"], "assistant should persist")
        self.assertEqual(plugin.msg_counter.get_counter(session_id), 2)
        self.assertEqual(len(summary_calls), 1)


class TestMemoryInjectionFormatting(unittest.TestCase):
    def test_extra_user_parts_uses_temp_text_part(self) -> None:
        req = types.SimpleNamespace(
            prompt="prompt",
            extra_user_content_parts=[types.SimpleNamespace(image_url="image")],
        )

        memory_operations._inject_via_extra_user_parts(req, "memory block", "prepend")

        injected = req.extra_user_content_parts[-1]
        self.assertEqual(injected.text, "memory block")
        self.assertTrue(injected._no_save)

    def test_extra_user_parts_prompt_fallback_respects_position(self) -> None:
        prepend_req = types.SimpleNamespace(prompt="prompt")
        append_req = types.SimpleNamespace(prompt="prompt")

        memory_operations._inject_via_extra_user_parts(prepend_req, "memory", "prepend")
        memory_operations._inject_via_extra_user_parts(append_req, "memory", "append")

        self.assertEqual(prepend_req.prompt, "memory\nprompt")
        self.assertEqual(append_req.prompt, "prompt\nmemory")

    def test_clean_contexts_extra_user_parts_leaves_context_history_untouched(self) -> None:
        plugin = _Plugin({"memory_injection_method": "extra_user_parts"})
        contexts = [
            {"role": "user", "content": "old <Mnemosyne>memory</Mnemosyne>"}
        ]
        req = types.SimpleNamespace(contexts=contexts, system_prompt="", prompt="")

        memory_operations.clean_contexts(plugin, req)

        self.assertIs(req.contexts, contexts)
        self.assertEqual(
            req.contexts[0]["content"], "old <Mnemosyne>memory</Mnemosyne>"
        )


class TestRemoveMnemosyneTags(unittest.TestCase):
    def test_remove_all_tags_preserves_user_message_metadata(self) -> None:
        message = {
            "role": "user",
            "content": "Hello <Mnemosyne>memory</Mnemosyne> world",
            "_no_save": True,
            "message_id": "preset-1",
        }

        cleaned = remove_mnemosyne_tags([message], contexts_memory_len=0)

        self.assertEqual(cleaned[0]["content"], "Hello  world")
        self.assertTrue(cleaned[0]["_no_save"])
        self.assertEqual(cleaned[0]["message_id"], "preset-1")
        self.assertEqual(
            message["content"], "Hello <Mnemosyne>memory</Mnemosyne> world"
        )

    def test_remove_all_tags_preserves_metadata_without_tags(self) -> None:
        message = {
            "role": "user",
            "content": "Plain preset message",
            "_no_save": True,
            "custom": {"source": "begin_dialogs"},
        }

        cleaned = remove_mnemosyne_tags([message], contexts_memory_len=0)

        self.assertEqual(cleaned[0]["content"], "Plain preset message")
        self.assertTrue(cleaned[0]["_no_save"])
        self.assertEqual(cleaned[0]["custom"], {"source": "begin_dialogs"})

    def test_tag_retention_preserves_metadata_for_cleaned_and_kept_tags(self) -> None:
        contents = [
            {
                "role": "user",
                "content": "old <Mnemosyne>first</Mnemosyne>",
                "_no_save": True,
                "message_id": "old",
            },
            {
                "role": "user",
                "content": "new <Mnemosyne>second</Mnemosyne>",
                "_no_save": True,
                "message_id": "new",
            },
        ]

        cleaned = remove_mnemosyne_tags(contents, contexts_memory_len=1)

        self.assertEqual(cleaned[0]["content"], "old ")
        self.assertTrue(cleaned[0]["_no_save"])
        self.assertEqual(cleaned[0]["message_id"], "old")
        self.assertEqual(cleaned[1]["content"], "new <Mnemosyne>second</Mnemosyne>")
        self.assertTrue(cleaned[1]["_no_save"])
        self.assertEqual(cleaned[1]["message_id"], "new")

    def test_multimodal_user_message_preserves_metadata(self) -> None:
        content_parts = [{"type": "text", "text": "hello"}]
        message = {
            "role": "user",
            "content": content_parts,
            "_no_save": True,
            "custom": "preserved",
        }

        cleaned = remove_mnemosyne_tags([message], contexts_memory_len=1)

        self.assertIs(cleaned[0]["content"], content_parts)
        self.assertTrue(cleaned[0]["_no_save"])
        self.assertEqual(cleaned[0]["custom"], "preserved")


class TestSummaryFormatting(unittest.TestCase):
    def test_turn_marker_dedupes_recreated_event_objects(self) -> None:
        plugin = _Plugin({})
        first_event = _TurnEvent("msg-1")
        second_event = _TurnEvent("msg-1")

        first_marker = _build_turn_marker(
            plugin, first_event, session_id=first_event.unified_msg_origin
        )
        second_marker = _build_turn_marker(
            plugin, second_event, session_id=second_event.unified_msg_origin
        )

        self.assertEqual(first_marker, second_marker)
        self.assertTrue(
            _mark_turn_once(
                plugin, "_mnemosyne_processed_request_turns", first_marker
            )
        )
        self.assertFalse(
            _mark_turn_once(
                plugin, "_mnemosyne_processed_request_turns", second_marker
            )
        )

    def test_empty_turn_marker_fails_closed(self) -> None:
        plugin = _Plugin({})

        self.assertFalse(
            _mark_turn_once(plugin, "_mnemosyne_processed_request_turns", "")
        )
        self.assertFalse(hasattr(plugin, "_mnemosyne_processed_request_turns"))

    def test_last_user_turn_store_is_bounded_lru(self) -> None:
        plugin = _Plugin({})
        for index in range(2050):
            _remember_last_user_turn(plugin, f"session-{index}", f"marker-{index}")

        store = _get_last_user_turn_store(plugin)

        self.assertEqual(len(store), 2048)
        self.assertNotIn("session-0", store)
        self.assertNotIn("session-1", store)
        self.assertEqual(store["session-2049"], "marker-2049")

    def test_single_arg_get_extra_preserves_explicit_none(self) -> None:
        event = _SingleArgExtraEvent({"stored": None})

        self.assertIsNone(_get_event_extra(event, "stored", "fallback"))
        self.assertIsNone(_get_event_extra(event, "missing", "fallback"))

    def test_format_context_excludes_tools_by_default(self) -> None:
        history = [
            {"role": "user", "content": "帮我查天气"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": "{\"city\":\"北京\"}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "北京晴，28度",
            },
            {"role": "assistant", "content": "北京今天晴，28度。"},
        ]

        text = format_context_to_string(history, 4)

        self.assertIn("user:帮我查天气", text)
        self.assertIn("assistant:北京今天晴，28度。", text)
        self.assertNotIn("tool result", text)
        self.assertNotIn("assistant called tool", text)

    def test_format_context_includes_tool_context_when_enabled(self) -> None:
        history = [
            {"role": "user", "content": "帮我查天气"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": "{\"city\":\"北京\"}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "北京晴，28度",
            },
            {"role": "assistant", "content": "北京今天晴，28度。"},
        ]

        text = format_context_to_string(
            history, 4, include_tool_context=True
        )

        self.assertIn("assistant called tool get_weather id=call_1", text)
        self.assertIn("tool result id=call_1: 北京晴，28度", text)
        self.assertIn("assistant:北京今天晴，28度。", text)

    def test_format_context_preserves_assistant_text_with_tool_calls_order(self) -> None:
        history = [
            {"role": "user", "content": "帮我查天气"},
            {
                "role": "assistant",
                "content": "我查一下。",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": "{\"city\":\"北京\"}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "北京晴，28度",
            },
            {"role": "assistant", "content": "北京今天晴，28度。"},
        ]

        text = format_context_to_string(
            history, 4, include_tool_context=True
        )

        self.assertLess(text.index("assistant:我查一下。"), text.index("assistant called tool"))
        self.assertLess(text.index("assistant called tool"), text.index("tool result"))
        self.assertLess(text.index("tool result"), text.index("assistant:北京今天晴，28度。"))

    def test_format_context_uses_multimodal_placeholders(self) -> None:
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看看这张图"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAAA"},
                    },
                ],
            },
            {
                "role": "assistant",
                "content": {
                    "type": "audio_url",
                    "audio_url": {"url": "data:audio/wav;base64,BBBB"},
                },
            },
            {"role": "user", "content": "base64://CCCC"},
            {"role": "assistant", "content": "data:audio/mp3;base64,DDDD"},
        ]

        text = format_context_to_string(history, 4)

        self.assertIn("user:看看这张图 [图片]", text)
        self.assertIn("assistant:[音频]", text)
        self.assertIn("user:[图片]", text)
        self.assertNotIn("AAAA", text)
        self.assertNotIn("BBBB", text)
        self.assertNotIn("CCCC", text)
        self.assertNotIn("DDDD", text)
        self.assertNotIn("data:image", text)
        self.assertNotIn("data:audio", text)
        self.assertNotIn("base64://", text)

    def test_format_context_keeps_dialog_length_separate_from_tool_context(self) -> None:
        history = [
            {"role": "user", "content": "帮我查天气"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "北京晴，28度",
            },
            {"role": "assistant", "content": "北京今天晴，28度。"},
        ]

        text = format_context_to_string(
            history, 2, include_tool_context=True
        )

        self.assertIn("tool result id=call_1: 北京晴，28度", text)
        self.assertIn("assistant:北京今天晴，28度。", text)
        self.assertIn("user:帮我查天气", text)

    def test_format_context_limits_tool_context_separately(self) -> None:
        history = [
            {"role": "user", "content": "帮我查天气"},
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "北京晴，28度",
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": "上海雨，24度",
            },
            {"role": "assistant", "content": "查好了。"},
        ]

        text = format_context_to_string(
            history, 2, include_tool_context=True, tool_context_limit=1
        )

        self.assertIn("user:帮我查天气", text)
        self.assertIn("assistant:查好了。", text)
        self.assertIn("tool result id=call_2: 上海雨，24度", text)
        self.assertNotIn("tool result id=call_1: 北京晴，28度", text)

    def test_format_context_does_not_pull_old_tool_context_outside_dialog_window(
        self,
    ) -> None:
        history = [
            {"role": "tool", "tool_call_id": f"old_{index}", "content": f"D{index}"}
            for index in range(20)
        ]
        history.extend(
            [
                {"role": "user", "content": "当前问题"},
                {"role": "assistant", "content": "当前回答"},
            ]
        )

        text = format_context_to_string(
            history,
            2,
            include_tool_context=True,
            tool_context_limit=12,
        )

        self.assertIn("user:当前问题", text)
        self.assertIn("assistant:当前回答", text)
        self.assertNotIn("tool result", text)
        self.assertNotIn("D0", text)
        self.assertNotIn("D19", text)

    def test_format_tool_calls_result_supports_model_objects(self) -> None:
        tool_result = _ToolCallsResult(
            _ToolCallsInfo([_ToolCall("call_2", "search_koko_tools", '{"query":"记忆"}')]),
            [_ToolResultMsg("call_2", "找到工具 remember_memory_vector")],
        )

        text = format_tool_calls_result_to_string([tool_result])

        self.assertIn("assistant called tool search_koko_tools id=call_2", text)
        self.assertIn('"query":"记忆"', text)
        self.assertIn("tool result id=call_2: 找到工具 remember_memory_vector", text)


class TestMessageCounter(unittest.TestCase):
    def test_adjust_counter_ignores_tool_context_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            counter = MessageCounter(plugin_data_dir=tmp_dir)
            try:
                session_id = "test-session"
                for _ in range(2):
                    counter.increment_counter(session_id)

                history = [
                    {"role": "user", "content": "查一下天气"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "weather",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "content": "晴",
                    },
                    {"role": "assistant", "content": "今天晴。"},
                ]

                self.assertTrue(
                    counter.adjust_counter_if_necessary(session_id, history)
                )
                self.assertEqual(counter.get_counter(session_id), 2)
            finally:
                counter.close()

    def test_adjust_counter_counts_assistant_text_with_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            counter = MessageCounter(plugin_data_dir=tmp_dir)
            try:
                session_id = "test-session"
                counter.increment_counter(session_id)
                counter.increment_counter(session_id)
                history = [
                    {"role": "user", "content": "查询天气"},
                    {
                        "role": "assistant",
                        "content": "我先帮你查询。",
                        "tool_calls": [{"id": "call_1", "type": "function"}],
                    },
                ]

                self.assertTrue(
                    counter.adjust_counter_if_necessary(session_id, history)
                )
                self.assertEqual(counter.get_counter(session_id), 2)
            finally:
                counter.close()


class TestConversationContextManager(unittest.TestCase):
    def test_clear_role_messages_removes_temporary_tool_context(self) -> None:
        manager = ConversationContextManager()
        session_id = "test-session"
        manager.add_message(session_id, "user", "查天气")
        manager.add_message(session_id, "tool", "tool result")
        manager.add_message(session_id, "assistant", "今天晴")

        removed = manager.clear_role_messages(session_id, "tool")
        history = manager.get_history(session_id)

        self.assertEqual(removed, 1)
        self.assertEqual([item["role"] for item in history], ["user", "assistant"])

    def test_trim_role_messages_keeps_recent_tool_context(self) -> None:
        manager = ConversationContextManager()
        session_id = "test-session"
        manager.add_message(session_id, "user", "查天气")
        for index in range(5):
            manager.add_message(session_id, "tool", f"tool-{index}")
        manager.add_message(session_id, "assistant", "今天晴")

        removed = manager.trim_role_messages(session_id, "tool", keep_last=2)
        history = manager.get_history(session_id)

        self.assertEqual(removed, 3)
        self.assertEqual(
            [(item["role"], item["content"]) for item in history],
            [
                ("user", "查天气"),
                ("tool", "tool-3"),
                ("tool", "tool-4"),
                ("assistant", "今天晴"),
            ],
        )

    def test_clear_role_messages_by_metadata_keeps_newer_tool_context(self) -> None:
        manager = ConversationContextManager()
        session_id = "test-session"
        manager.add_message(
            session_id,
            "tool",
            "old tool",
            metadata={"turn_marker": "old"},
        )
        manager.add_message(
            session_id,
            "tool",
            "new tool",
            metadata={"turn_marker": "new"},
        )

        removed = manager.clear_role_messages_by_metadata(
            session_id, "tool", "turn_marker", {"old"}
        )
        history = manager.get_history(session_id)

        self.assertEqual(removed, 1)
        self.assertEqual([item["content"] for item in history], ["new tool"])


class TestSummaryToolContextCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_callback_cleans_captured_tool_context_after_failure_and_cancel(
        self,
    ) -> None:
        plugin = _MemoryPlugin()
        session_id = "test-session"
        marker_key = memory_operations.TOOL_CONTEXT_MARKER_METADATA_KEY

        plugin.context_manager.add_message(
            session_id,
            "tool",
            "failed summary tool",
            metadata={marker_key: "failed"},
        )

        async def failing_summary() -> None:
            raise RuntimeError("summary failed")

        failed_task = asyncio.create_task(failing_summary())
        memory_operations._attach_summary_task_callback(
            failed_task, plugin, session_id, {"failed"}
        )
        with self.assertRaises(RuntimeError):
            await failed_task
        await asyncio.sleep(0)
        self.assertEqual(plugin.context_manager.get_history(session_id), [])

        plugin.context_manager.add_message(
            session_id,
            "tool",
            "cancelled summary tool",
            metadata={marker_key: "cancelled"},
        )

        async def pending_summary() -> None:
            await asyncio.Future()

        cancelled_task = asyncio.create_task(pending_summary())
        memory_operations._attach_summary_task_callback(
            cancelled_task, plugin, session_id, {"cancelled"}
        )
        plugin.context_manager.add_message(
            session_id,
            "tool",
            "newer tool",
            metadata={marker_key: "newer"},
        )
        cancelled_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled_task
        await asyncio.sleep(0)

        history = plugin.context_manager.get_history(session_id)
        self.assertEqual([item["content"] for item in history], ["newer tool"])


class TestLightweightGraphMetadata(unittest.TestCase):
    def test_build_metadata_collects_entities_relations_and_participants(self) -> None:
        summary = "Alice met Bob in Paris. Bob discussed ProjectX with Carol."
        context_history = [
            {"role": "user", "metadata": {"speaker_id": "u1"}},
            {"role": "assistant", "metadata": {"speaker_id": "assistant"}},
            {"role": "user", "metadata": {"speaker_id": "u1"}},
            {"role": "user", "metadata": {"speaker_id": "u2"}},
        ]

        metadata = _build_lightweight_graph_metadata(summary, context_history)
        relations_as_tuples = {tuple(edge) for edge in metadata.get("relations", [])}

        self.assertIn("alice", metadata.get("entities", []))
        self.assertIn("bob", metadata.get("entities", []))
        self.assertIn(("alice", "bob"), relations_as_tuples)
        self.assertEqual(metadata.get("participants"), ["u1", "u2"])
        self.assertIn("recorded_at", metadata)


class TestPostProcessSearchResults(unittest.TestCase):
    def test_keyword_rerank_prioritizes_keyword_hit(self) -> None:
        plugin = _Plugin(
            {"use_participant_filtering": False, "use_lightweight_memory_graph": False}
        )
        detailed_results = [
            {"content": "no direct term", "_distance": 0.01},
            {"content": "contains alpha term", "_distance": 0.9},
        ]

        ranked = _post_process_search_results(
            plugin=plugin,
            detailed_results=detailed_results,
            query_text="alpha",
            sender_id=None,
        )

        self.assertEqual(ranked[0]["content"], "contains alpha term")

    def test_participant_filtering_keeps_matching_and_legacy_records(self) -> None:
        plugin = _Plugin(
            {"use_participant_filtering": True, "use_lightweight_memory_graph": False}
        )
        detailed_results = [
            {
                "content": pack_memory_content(
                    "for user2", {"participants": ["u2"], "relations": []}
                )
            },
            {"content": "legacy record without metadata"},
            {
                "content": pack_memory_content(
                    "for user1", {"participants": ["u1"], "relations": []}
                )
            },
        ]

        filtered = _post_process_search_results(
            plugin=plugin,
            detailed_results=detailed_results,
            query_text="",
            sender_id=" u1 ",
        )

        self.assertEqual(
            [item["content"] for item in filtered],
            ["legacy record without metadata", "for user1"],
        )

    def test_graph_expansion_can_change_ranking(self) -> None:
        base_results = [
            {"content": "neutral record", "_distance": 0.01},
            {
                "content": pack_memory_content(
                    "memory about bravo",
                    {"relations": [["alpha", "bravo"]], "participants": []},
                ),
                "_distance": 0.9,
            },
        ]

        plugin_without_graph = _Plugin(
            {"use_participant_filtering": False, "use_lightweight_memory_graph": False}
        )
        ranked_without_graph = _post_process_search_results(
            plugin=plugin_without_graph,
            detailed_results=base_results,
            query_text="alpha",
            sender_id=None,
        )

        plugin_with_graph = _Plugin(
            {"use_participant_filtering": False, "use_lightweight_memory_graph": True}
        )
        ranked_with_graph = _post_process_search_results(
            plugin=plugin_with_graph,
            detailed_results=base_results,
            query_text="alpha",
            sender_id=None,
        )

        self.assertEqual(ranked_without_graph[0]["content"], "neutral record")
        self.assertEqual(ranked_with_graph[0]["content"], "memory about bravo")


class _Sender:
    def __init__(self, nickname=None, user_id=None):
        self.nickname = nickname
        self.user_id = user_id


class _MessageObj:
    def __init__(self, sender):
        self.sender = sender


class _EventForIdentity:
    def __init__(self, sender_id=None, sender=None, message_obj=None):
        self._sender_id = sender_id
        self.sender = sender
        self.message_obj = message_obj

    def get_sender_id(self):
        return self._sender_id


class TestSenderIdentityResolution(unittest.TestCase):
    def test_resolve_sender_identity_fallbacks_private_session_id(self) -> None:
        event = _EventForIdentity()
        sender_name, sender_id = _resolve_sender_identity(
            event,
            "default:FriendMessage:user_1001",
        )

        self.assertEqual(sender_name, "用户")
        self.assertEqual(sender_id, "user_1001")

    def test_resolve_sender_identity_prefers_message_sender(self) -> None:
        event = _EventForIdentity(
            sender_id=None,
            message_obj=_MessageObj(_Sender(nickname="test_user")),
        )
        sender_name, sender_id = _resolve_sender_identity(
            event,
            "default:FriendMessage:user_2002",
        )

        self.assertEqual(sender_name, "test_user")
        self.assertEqual(sender_id, "user_2002")

    def test_resolve_sender_identity_prefers_get_sender_id(self) -> None:
        event = _EventForIdentity(
            sender_id="preferred_id",
            sender={"nickname": "sender_user", "user_id": "sender_fallback_id"},
            message_obj=_MessageObj(
                _Sender(nickname="message_user", user_id="message_fallback_id")
            ),
        )
        sender_name, sender_id = _resolve_sender_identity(
            event,
            "default:FriendMessage:session_fallback_id",
        )

        self.assertEqual(sender_name, "message_user")
        self.assertEqual(sender_id, "preferred_id")

    def test_resolve_sender_identity_ignores_non_private_session_fallback(self) -> None:
        event = _EventForIdentity()
        sender_name, sender_id = _resolve_sender_identity(
            event,
            "default:NotFriendMessage:user_3003",
        )

        self.assertEqual(sender_name, "用户")
        self.assertEqual(sender_id, "")

    def test_build_identity_prefixed_user_text(self) -> None:
        with_id = _build_identity_prefixed_user_text("hello", "test_user", "user_2002")
        without_id = _build_identity_prefixed_user_text("hello", "test_user", "")

        # basic formatting
        self.assertEqual(with_id, "[test_user(user_2002)]: hello")
        self.assertEqual(without_id, "[test_user]: hello")

        # default-name behavior for None / whitespace sender_name
        default_name = _build_identity_prefixed_user_text("hello", None, "user_2003")
        whitespace_name = _build_identity_prefixed_user_text("hello", "   ", "user_2004")

        self.assertEqual(default_name, "[用户(user_2003)]: hello")
        self.assertEqual(whitespace_name, "[用户(user_2004)]: hello")

        # non-string sender_id should be stringified
        numeric_id = _build_identity_prefixed_user_text("hello", "test_user", 123)
        self.assertEqual(numeric_id, "[test_user(123)]: hello")

        # non-string message_text should be converted via str()
        numeric_message = _build_identity_prefixed_user_text(42, "test_user", "user_2005")
        self.assertEqual(numeric_message, "[test_user(user_2005)]: 42")


if __name__ == "__main__":
    unittest.main()
