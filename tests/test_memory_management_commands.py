from __future__ import annotations

import json

import pytest

from core import commands
from core.security_utils import safe_build_milvus_expression
from memory_manager.vector_db_base import VectorDeleteResult, VectorInsertResult


class _SyntheticEvent:
    unified_msg_origin = "synthetic-platform:GroupMessage:synthetic-group"

    def get_sender_id(self):
        return "synthetic-admin"

    def plain_result(self, message: str):
        return message


class _SyntheticVectorDB:
    def __init__(self):
        self.records = [
            {
                "id": "record-old",
                "memory_id": "wrong-metadata-id",
                "content": "synthetic legacy note",
                "create_time": 1_700_000_000,
                "session_id": _SyntheticEvent.unified_msg_origin,
                "personality_id": "default",
            },
            {
                "id": "record-current",
                "memory_id": "wrong-metadata-id-current",
                "content": "synthetic current note",
                "create_time": 1_800_000_000,
                "session_id": _SyntheticEvent.unified_msg_origin,
                "personality_id": "default",
            },
            {
                "id": "record-other-session",
                "memory_id": "wrong-metadata-id-other",
                "content": "synthetic other-session note",
                "create_time": 1_700_000_000,
                "session_id": "synthetic-platform:GroupMessage:another-group",
                "personality_id": "default",
            },
        ]
        self.deleted = []
        self.inserted = []
        self.flushed = False

    def is_connected(self):
        return True

    def query(self, collection_name, filters, output_fields, limit=None, offset=None):
        return list(self.records)

    def delete(self, collection_name, expr):
        self.deleted.append((collection_name, expr))
        return VectorDeleteResult(delete_count=1)

    def insert(self, collection_name, data):
        self.inserted.extend(data)
        return VectorInsertResult(insert_count=len(data))

    def flush(self, collection_names=None):
        self.flushed = True
        return True


class _SyntheticEmbeddingProvider:
    async def get_embedding(self, content: str):
        return [float(len(content)), 1.0]


class _SyntheticPlugin:
    collection_name = "default"
    config = {"vector_db_type": "chroma"}

    def __init__(self, plugin_data_dir):
        self.plugin_data_dir = str(plugin_data_dir)
        self.vector_db = _SyntheticVectorDB()
        self.embedding_provider = _SyntheticEmbeddingProvider()


async def _collect_results(generator):
    return [result async for result in generator]


def test_time_and_native_id_filters_are_safe():
    assert safe_build_milvus_expression("create_time", 123.5, "<") == (
        "create_time < 123.5"
    )
    assert safe_build_milvus_expression("id", "record-old", "==") == (
        'id == "record-old"'
    )


@pytest.mark.asyncio
async def test_delete_before_previews_then_deletes_only_current_session(tmp_path):
    plugin = _SyntheticPlugin(tmp_path)
    event = _SyntheticEvent()

    preview = await _collect_results(
        commands.delete_before_memory_cmd_impl(plugin, event, "2026-07-15")
    )
    assert plugin.vector_db.deleted == []
    assert "--confirm" in preview[0]

    confirmed = await _collect_results(
        commands.delete_before_memory_cmd_impl(
            plugin,
            event,
            "2026-07-15",
            confirm="--confirm",
        )
    )
    assert plugin.vector_db.deleted == [("default", 'id == "record-old"')]
    assert plugin.vector_db.flushed
    assert "已执行" in confirmed[0]


@pytest.mark.asyncio
async def test_delete_between_uses_a_half_open_range(tmp_path):
    plugin = _SyntheticPlugin(tmp_path)
    event = _SyntheticEvent()

    results = await _collect_results(
        commands.delete_between_memory_cmd_impl(
            plugin,
            event,
            "2023-01-01",
            "2026-07-15",
            confirm="--confirm",
        )
    )

    assert plugin.vector_db.deleted == [("default", 'id == "record-old"')]
    assert "时间范围删除已执行" in results[0]


@pytest.mark.asyncio
async def test_export_then_import_uses_an_export_directory_and_requires_confirmation(
    tmp_path,
):
    plugin = _SyntheticPlugin(tmp_path)
    event = _SyntheticEvent()

    exported = await _collect_results(
        commands.export_memory_cmd_impl(plugin, event, "synthetic-export")
    )
    export_path = tmp_path / "exports" / "synthetic-export.json"
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["format"] == "mnemosyne-memory-export"
    assert len(payload["records"]) == 2
    assert "导出完成" in exported[0]

    preview = await _collect_results(
        commands.import_memory_cmd_impl(plugin, event, "synthetic-export.json")
    )
    assert plugin.vector_db.inserted == []
    assert "当前只是预览" in preview[0]

    imported = await _collect_results(
        commands.import_memory_cmd_impl(
            plugin,
            event,
            "synthetic-export.json",
            confirm="--confirm",
        )
    )
    assert len(plugin.vector_db.inserted) == 2
    assert all("embedding" in record for record in plugin.vector_db.inserted)
    assert "导入完成" in imported[0]


@pytest.mark.asyncio
async def test_stats_and_search_default_to_the_current_session(tmp_path):
    plugin = _SyntheticPlugin(tmp_path)
    event = _SyntheticEvent()

    stats = await _collect_results(commands.stats_memory_cmd_impl(plugin, event))
    search = await _collect_results(
        commands.search_memory_cmd_impl(plugin, event, "current")
    )

    assert "记忆数量：2" in stats[0]
    assert "record-current" in search[0]
    assert "other-session" not in search[0]


@pytest.mark.asyncio
async def test_stats_and_search_accept_all_sessions_only_with_the_flag(tmp_path):
    plugin = _SyntheticPlugin(tmp_path)
    event = _SyntheticEvent()

    stats = await _collect_results(
        commands.stats_memory_cmd_impl(plugin, event, "--all")
    )
    search = await _collect_results(
        commands.search_memory_cmd_impl(plugin, event, "other-session", "--all")
    )

    assert "会话数量：2" in stats[0]
    assert "record-other-session" in search[0]
