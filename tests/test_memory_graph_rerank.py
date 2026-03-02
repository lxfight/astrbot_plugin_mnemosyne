from __future__ import annotations

import sys
import types
import unittest


def _ensure_dependency_stubs() -> None:
    if "astrbot" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api_event = types.ModuleType("astrbot.api.event")
        astrbot_api_provider = types.ModuleType("astrbot.api.provider")
        astrbot_core = types.ModuleType("astrbot.core")
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

        astrbot_api.logger = _Logger()
        astrbot_api_event.AstrMessageEvent = _AstrMessageEvent
        astrbot_api_provider.ProviderRequest = _ProviderRequest
        astrbot_api_provider.LLMResponse = _LLMResponse
        astrbot_core_log.LogManager = _LogManager

        astrbot.api = astrbot_api
        astrbot.core = astrbot_core
        astrbot_core.log = astrbot_core_log

        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
        sys.modules["astrbot.api.event"] = astrbot_api_event
        sys.modules["astrbot.api.provider"] = astrbot_api_provider
        sys.modules["astrbot.core"] = astrbot_core
        sys.modules["astrbot.core.log"] = astrbot_core_log

    if "pymilvus.exceptions" not in sys.modules:
        pymilvus = types.ModuleType("pymilvus")
        pymilvus_exceptions = types.ModuleType("pymilvus.exceptions")

        class _MilvusException(Exception):
            pass

        pymilvus_exceptions.MilvusException = _MilvusException
        pymilvus.exceptions = pymilvus_exceptions
        sys.modules["pymilvus"] = pymilvus
        sys.modules["pymilvus.exceptions"] = pymilvus_exceptions


_ensure_dependency_stubs()

from core.memory_operations import (  # noqa: E402
    _build_lightweight_graph_metadata,
    _post_process_search_results,
)
from core.tools import (  # noqa: E402
    extract_query_keywords,
    pack_memory_content,
    resolve_max_prompt_chars,
    split_memory_content_meta,
    strip_memory_meta,
    truncate_for_embedding,
)


class _Plugin:
    def __init__(self, config: dict):
        self.config = config


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


if __name__ == "__main__":
    unittest.main()
