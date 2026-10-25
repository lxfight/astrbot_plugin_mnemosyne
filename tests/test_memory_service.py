"""
管理面板记忆服务测试。
"""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

if "astrbot.api" not in sys.modules:
    astrbot = types.ModuleType("astrbot")
    astrbot_api = types.ModuleType("astrbot.api")

    class _Logger:
        def info(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

    astrbot_api.logger = _Logger()
    astrbot.api = astrbot_api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = astrbot_api


from admin_panel.services.memory_service import MemoryService  # noqa: E402
from admin_panel.models.memory import MemorySearchRequest  # noqa: E402
from core.tools import pack_memory_content  # noqa: E402
from memory_manager.vector_db_base import (  # noqa: E402
    VectorDeleteResult,
    VectorInsertResult,
)


class _FakeVectorDB:
    def __init__(self):
        self.deleted_expr = None
        self.flushed = False
        self.operation_thread_ids = []

    def is_connected(self):
        return True

    def has_collection(self, _collection_name):
        return True

    def delete(self, collection_name, expr):
        self.operation_thread_ids.append(threading.get_ident())
        self.deleted_expr = (collection_name, expr)
        return VectorDeleteResult(delete_count=1)

    def flush(self, _collection_names):
        self.operation_thread_ids.append(threading.get_ident())
        self.flushed = True


class _Plugin:
    def __init__(self, vector_db_type):
        self.config = {"vector_db_type": vector_db_type}
        self.collection_name = "memory_collection"
        self.vector_db = _FakeVectorDB()


@pytest.mark.asyncio
async def test_delete_memory_uses_native_id_for_non_milvus():
    plugin = _Plugin("chroma")
    service = MemoryService(plugin)
    event_loop_thread = threading.get_ident()

    assert await service.delete_memory("native-id_1")
    assert plugin.vector_db.deleted_expr == (
        "memory_collection",
        'id == "native-id_1"',
    )
    assert plugin.vector_db.flushed
    assert all(
        thread_id != event_loop_thread
        for thread_id in plugin.vector_db.operation_thread_ids
    )


@pytest.mark.asyncio
async def test_delete_memory_uses_memory_id_for_milvus():
    plugin = _Plugin("milvus")
    service = MemoryService(plugin)

    assert await service.delete_memory("123")
    assert plugin.vector_db.deleted_expr == (
        "memory_collection",
        "memory_id == 123",
    )


class _EmbeddingProvider:
    async def get_embedding(self, text):
        return [float(len(text)), 0.5]


class _UpdateVectorDB:
    def __init__(self, backend="chroma", fail_first_insert=False, metadata=None):
        self.backend = backend
        self.fail_first_insert = fail_first_insert
        self.metadata = metadata
        self.updated = None
        self.deleted_expr = None
        self.inserted = []
        self.flushed = False

    def is_connected(self):
        return True

    def has_collection(self, _collection_name):
        return True

    def get_by_id(self, **kwargs):
        record = {
            "session_id": "session-1",
            "content": pack_memory_content("原始记忆", self.metadata),
            "create_time": 1700000000,
            "personality_id": "persona-1",
        }
        if self.backend == "milvus":
            record["memory_id"] = 42
        else:
            record["id"] = "native-42"
        return record

    def update(self, collection_name, record_id, data):
        self.updated = (collection_name, record_id, data)
        return VectorInsertResult(insert_count=1, primary_keys=[record_id])

    def delete(self, collection_name, expr):
        self.deleted_expr = (collection_name, expr)
        return VectorDeleteResult(delete_count=1)

    def insert(self, collection_name, data):
        self.inserted.append((collection_name, data[0]))
        if self.fail_first_insert and len(self.inserted) == 1:
            return VectorInsertResult()
        return VectorInsertResult(
            insert_count=1,
            primary_keys=[100 + len(self.inserted)],
        )

    def flush(self, _collection_names):
        self.flushed = True


class _UpdatePlugin:
    def __init__(self, backend="chroma", fail_first_insert=False, metadata=None):
        self.config = {"vector_db_type": backend}
        self.collection_name = "memory_collection"
        self.vector_db = _UpdateVectorDB(backend, fail_first_insert, metadata)
        self.embedding_provider = _EmbeddingProvider()


@pytest.mark.asyncio
async def test_update_memory_preserves_native_id_and_regenerates_embedding():
    plugin = _UpdatePlugin("chroma")
    service = MemoryService(plugin)

    result = await service.update_memory("native-42", "更新后的记忆")

    assert result["memory_id"] == "native-42"
    assert result["id_changed"] is False
    assert result["embedding_regenerated"] is True
    assert plugin.vector_db.updated[1] == "native-42"
    assert plugin.vector_db.updated[2]["content"] == "更新后的记忆"
    assert plugin.vector_db.updated[2]["embedding"] == [6.0, 0.5]
    assert plugin.vector_db.flushed


@pytest.mark.asyncio
async def test_update_memory_preserves_hidden_metadata_and_embeds_visible_content():
    metadata = {"participants": ["user-1"], "relations": [["alice", "bob"]]}
    plugin = _UpdatePlugin("chroma", metadata=metadata)
    service = MemoryService(plugin)

    result = await service.update_memory("native-42", "更新后的记忆")

    assert plugin.vector_db.updated[2]["content"] == pack_memory_content(
        "更新后的记忆", metadata
    )
    assert plugin.vector_db.updated[2]["embedding"] == [6.0, 0.5]
    assert result["content"] == "更新后的记忆"


@pytest.mark.asyncio
async def test_update_memory_replaces_milvus_auto_id():
    metadata = {"source": "summary"}
    plugin = _UpdatePlugin("milvus", metadata=metadata)
    service = MemoryService(plugin)

    result = await service.update_memory("42", "新的 Milvus 记忆")

    assert plugin.vector_db.deleted_expr == (
        "memory_collection",
        "memory_id == 42",
    )
    assert result["memory_id"] == "101"
    assert result["previous_memory_id"] == "42"
    assert result["id_changed"] is True
    assert plugin.vector_db.inserted[0][1]["content"] == pack_memory_content(
        "新的 Milvus 记忆", metadata
    )


@pytest.mark.asyncio
async def test_update_memory_rolls_back_milvus_when_insert_fails():
    metadata = {"participants": ["user-1"]}
    plugin = _UpdatePlugin("milvus", fail_first_insert=True, metadata=metadata)
    service = MemoryService(plugin)

    with pytest.raises(RuntimeError, match="原内容已恢复"):
        await service.update_memory("42", "无法写入的新内容")

    assert len(plugin.vector_db.inserted) == 2
    rollback_payload = plugin.vector_db.inserted[1][1]
    assert rollback_payload["content"] == pack_memory_content("原始记忆", metadata)
    assert rollback_payload["embedding"] == [4.0, 0.5]


class _MetadataQueryVectorDB:
    def is_connected(self):
        return True

    def has_collection(self, _collection_name):
        return True

    def count(self, _collection_name, _filters=None):
        return 1

    def query(self, **_kwargs):
        return [
            {
                "id": "1",
                "memory_id": "1",
                "session_id": "session-1",
                "content": pack_memory_content(
                    "visible memory", {"participants": ["user-secret"]}
                ),
                "create_time": 1700000000,
            }
        ]

    def search(self, **_kwargs):
        return [
            {
                "id": "1",
                "memory_id": "1",
                "session_id": "session-1",
                "content": pack_memory_content(
                    "visible memory", {"participants": ["user-secret"]}
                ),
                "create_time": 1700000000,
                "_score": 0.9,
            }
        ]


@pytest.mark.asyncio
async def test_search_memories_hides_metadata_from_content_and_keyword_matching():
    plugin = _QueryPlugin()
    plugin.vector_db = _MetadataQueryVectorDB()
    plugin.embedding_provider = _EmbeddingProvider()
    service = MemoryService(plugin)

    response = await service.search_memories(MemorySearchRequest(limit=10))
    hidden_keyword = await service.search_memories(
        MemorySearchRequest(keyword="user-secret", limit=10)
    )
    vector_results = await service.vector_search("visible")
    stats = await service.get_memory_statistics()

    assert response.records[0].content == "visible memory"
    assert hidden_keyword.total_count == 0
    assert vector_results[0]["content"] == "visible memory"
    assert stats.average_memory_length == len("visible memory")


class _QueryVectorDB:
    def __init__(self):
        self.count_calls = 0
        self.deleted_expr = None
        self.query_calls = 0
        self.count_thread_ids = []
        self.query_thread_ids = []

    def is_connected(self):
        return True

    def has_collection(self, _collection_name):
        return True

    def count(self, _collection_name, _filters=None):
        self.count_calls += 1
        self.count_thread_ids.append(threading.get_ident())
        return 2

    def query(self, **_kwargs):
        self.query_calls += 1
        self.query_thread_ids.append(threading.get_ident())
        now = time.time()
        return [
            {
                "id": "1",
                "memory_id": "1",
                "session_id": "session-1",
                "content": "abc",
                "create_time": now,
            },
            {
                "id": "2",
                "memory_id": "2",
                "session_id": "session-2",
                "content": "defg",
                "create_time": now - 60,
            },
        ]

    def delete(self, collection_name, expr):
        self.deleted_expr = (collection_name, expr)
        return VectorDeleteResult(delete_count=1)

    def flush(self, _collection_names):
        return True


class _PagedVectorDB:
    def __init__(self, total, supports_count=True):
        self.total = total
        self.supports_count = supports_count
        self.count_calls = 0
        self.query_calls = 0
        self.query_limits = []
        self.query_offsets = []

    def is_connected(self):
        return True

    def has_collection(self, _collection_name):
        return True

    def count(self, _collection_name, _filters=None):
        self.count_calls += 1
        return self.total if self.supports_count else None

    def query(self, **kwargs):
        self.query_calls += 1
        limit = kwargs.get("limit")
        offset = kwargs.get("offset") or 0
        self.query_limits.append(limit)
        self.query_offsets.append(offset)
        end = min(offset + limit, self.total)
        return [
            {
                "id": str(index),
                "memory_id": str(index),
                "session_id": f"session-{index % 10}",
                "content": "memory",
                "create_time": 1_700_000_000 + index,
            }
            for index in range(offset, end)
        ]


class _QueryPlugin:
    def __init__(self):
        self.config = {"vector_db_type": "chroma"}
        self.collection_name = "memory_collection"
        self.vector_db = _QueryVectorDB()


class _BatchDeleteVectorDB:
    def __init__(self):
        self.expressions = []
        self.flush_count = 0

    def is_connected(self):
        return True

    def has_collection(self, _collection_name):
        return True

    def delete(self, _collection_name, expr):
        self.expressions.append(expr)
        return VectorDeleteResult()

    def flush(self, _collection_names):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_batch_delete_chunks_expressions_and_flushes_once():
    plugin = _QueryPlugin()
    plugin.vector_db = _BatchDeleteVectorDB()
    service = MemoryService(plugin)
    memory_ids = [f"memory-{index}" for index in range(401)]

    deleted_count = await service.batch_delete_memories(memory_ids)

    assert deleted_count == 401
    assert len(plugin.vector_db.expressions) == 3
    assert plugin.vector_db.expressions[0].count(" or ") == 199
    assert plugin.vector_db.expressions[1].count(" or ") == 199
    assert plugin.vector_db.expressions[2].count(" or ") == 0
    assert plugin.vector_db.flush_count == 1


@pytest.mark.asyncio
async def test_batch_delete_deduplicates_memory_ids():
    plugin = _QueryPlugin()
    plugin.vector_db = _BatchDeleteVectorDB()
    service = MemoryService(plugin)

    deleted_count = await service.batch_delete_memories(["1", "1", "2"])

    assert deleted_count == 2
    assert plugin.vector_db.expressions == ['id == "1" or id == "2"']
    assert plugin.vector_db.flush_count == 1


@pytest.mark.asyncio
async def test_memory_statistics_uses_short_ttl_cache_and_invalidates_on_delete():
    plugin = _QueryPlugin()
    service = MemoryService(plugin)

    first = await service.get_memory_statistics()
    second = await service.get_memory_statistics()

    assert first.total_memories == 2
    assert second is first
    assert plugin.vector_db.query_calls == 1

    await service.delete_memory("1")
    await service.get_memory_statistics()

    assert plugin.vector_db.query_calls == 2


@pytest.mark.asyncio
async def test_session_list_uses_short_ttl_cache():
    plugin = _QueryPlugin()
    service = MemoryService(plugin)

    first = await service.get_session_list(limit=1)
    second = await service.get_session_list(limit=2)

    assert len(first) == 1
    assert len(second) == 2
    assert plugin.vector_db.query_calls == 1


@pytest.mark.asyncio
async def test_search_latest_page_across_query_batches():
    plugin = _QueryPlugin()
    plugin.vector_db = _PagedVectorDB(total=2500)
    service = MemoryService(plugin)

    response = await service.search_memories(
        MemorySearchRequest(limit=1, sort_order="desc")
    )

    assert response.total_count == 2500
    assert response.records[0].memory_id == "2499"
    assert plugin.vector_db.count_calls == 1
    assert plugin.vector_db.query_limits == [2000, 500]


@pytest.mark.asyncio
async def test_memory_statistics_scans_all_query_batches():
    plugin = _QueryPlugin()
    plugin.vector_db = _PagedVectorDB(total=10050)
    service = MemoryService(plugin)

    stats = await service.get_memory_statistics()

    assert stats.total_memories == 10050
    assert stats.total_sessions == 10
    assert sum(stats.memories_by_session.values()) == 10050
    assert plugin.vector_db.count_calls == 1
    assert plugin.vector_db.query_limits == [2000, 2000, 2000, 2000, 2000, 50]


@pytest.mark.asyncio
async def test_memory_statistics_falls_back_without_native_count():
    plugin = _QueryPlugin()
    plugin.vector_db = _PagedVectorDB(total=3, supports_count=False)
    service = MemoryService(plugin)

    stats = await service.get_memory_statistics()

    assert stats.total_memories == 3
    assert plugin.vector_db.count_calls == 1
    assert plugin.vector_db.query_calls == 1


@pytest.mark.asyncio
async def test_session_list_aggregates_all_query_batches():
    plugin = _QueryPlugin()
    plugin.vector_db = _PagedVectorDB(total=10050)
    service = MemoryService(plugin)

    sessions = await service.get_session_list(limit=10)

    assert sum(session["memory_count"] for session in sessions) == 10050
    assert plugin.vector_db.query_limits == [2000, 2000, 2000, 2000, 2000, 2000]


@pytest.mark.asyncio
async def test_delete_session_uses_native_count():
    plugin = _QueryPlugin()
    service = MemoryService(plugin)

    deleted_count = await service.delete_session_memories("session-1")

    assert deleted_count == 2
    assert plugin.vector_db.query_calls == 0
    assert plugin.vector_db.deleted_expr == (
        "memory_collection",
        'session_id == "session-1"',
    )


@pytest.mark.asyncio
async def test_search_memories_runs_query_off_event_loop_thread():
    plugin = _QueryPlugin()
    service = MemoryService(plugin)
    event_loop_thread = threading.get_ident()

    response = await service.search_memories(MemorySearchRequest(limit=1))

    assert response.total_count == 2
    assert plugin.vector_db.count_thread_ids
    assert all(
        thread_id != event_loop_thread
        for thread_id in plugin.vector_db.count_thread_ids
    )
    assert plugin.vector_db.query_thread_ids
    assert all(
        thread_id != event_loop_thread
        for thread_id in plugin.vector_db.query_thread_ids
    )
