import asyncio
import threading
from collections import OrderedDict
from types import SimpleNamespace

import core.migration_utils as migration_utils
import pytest
from core.migration_utils import (
    MIGRATION_CHECKED_LIMIT,
    MIGRATION_QUERY_LIMIT,
    _mark_migration_checked,
    migrate_session_data_if_needed,
)


class _UpsertResult:
    def __init__(self, count: int):
        self.upsert_count = count


class _Collection:
    def __init__(self):
        self.upserted: list[dict] = []

    def upsert(self, data: list[dict]):
        self.upserted.extend(data)
        return _UpsertResult(len(data))


class _Manager:
    def __init__(self, results=None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.query_calls = 0
        self.query_args: list[dict] = []
        self.collection = _Collection()
        self.flushed: list[list[str]] = []

    def is_connected(self) -> bool:
        return True

    def query(self, **kwargs):
        self.query_calls += 1
        self.query_args.append(kwargs)
        if self.error:
            raise self.error
        return self.results

    def get_collection(self, _name: str):
        return self.collection

    def flush(self, names: list[str]) -> None:
        self.flushed.append(names)


def _plugin(manager: _Manager):
    return SimpleNamespace(
        milvus_manager=manager,
        _migrated_sessions=OrderedDict(),
        _migration_inflight=set(),
    )


@pytest.mark.asyncio
async def test_migration_uses_one_query_and_updates_legacy_sessions():
    manager = _Manager(
        results=[
            {"memory_id": 1, "session_id": "conv!u1", "content": "one"},
            {"memory_id": 2, "session_id": "u1", "content": "two"},
            {"memory_id": 3, "session_id": "telegram:GroupMessage:bot!conv!u1"},
        ]
    )
    plugin = _plugin(manager)
    unified_origin = "telegram:GroupMessage:bot!conv!u1"

    await migrate_session_data_if_needed(plugin, unified_origin, "memories")

    assert manager.query_calls == 1
    query = manager.query_args[0]
    assert query["output_fields"] == ["*"]
    assert " or " in query["expression"]
    assert "conv!u1" in query["expression"]
    assert [item["memory_id"] for item in manager.collection.upserted] == [1, 2]
    assert all(
        item["session_id"] == unified_origin for item in manager.collection.upserted
    )
    assert manager.flushed == [["memories"]]
    assert unified_origin in plugin._migrated_sessions


@pytest.mark.asyncio
async def test_checked_session_is_not_queried_again():
    manager = _Manager(results=[])
    plugin = _plugin(manager)

    await migrate_session_data_if_needed(
        plugin, "telegram:GroupMessage:conv-1", "memories"
    )
    await migrate_session_data_if_needed(
        plugin, "telegram:GroupMessage:conv-1", "memories"
    )

    assert manager.query_calls == 1


@pytest.mark.asyncio
async def test_concurrent_calls_share_one_inflight_migration(monkeypatch):
    plugin = _plugin(_Manager())
    started = threading.Event()
    release = threading.Event()
    calls = 0

    def slow_migration(*_args) -> bool:
        nonlocal calls
        calls += 1
        started.set()
        assert release.wait(2)
        return True

    monkeypatch.setattr(
        migration_utils, "_migrate_session_data_sync", slow_migration
    )

    first = asyncio.create_task(
        migrate_session_data_if_needed(
            plugin, "telegram:GroupMessage:conv-1", "memories"
        )
    )
    assert await asyncio.to_thread(started.wait, 2)
    second = asyncio.create_task(
        migrate_session_data_if_needed(
            plugin, "telegram:GroupMessage:conv-1", "memories"
        )
    )
    await second

    assert calls == 1
    release.set()
    await first


@pytest.mark.asyncio
async def test_query_failure_does_not_mark_session_checked():
    manager = _Manager(error=RuntimeError("milvus unavailable"))
    plugin = _plugin(manager)
    unified_origin = "telegram:GroupMessage:conv-1"

    await migrate_session_data_if_needed(plugin, unified_origin, "memories")
    await migrate_session_data_if_needed(plugin, unified_origin, "memories")

    assert manager.query_calls == 2
    assert unified_origin not in plugin._migrated_sessions


def test_checked_session_markers_are_bounded():
    plugin = _plugin(_Manager())
    for index in range(MIGRATION_CHECKED_LIMIT + 1):
        _mark_migration_checked(plugin, f"session-{index}")

    assert len(plugin._migrated_sessions) == MIGRATION_CHECKED_LIMIT
    assert "session-0" not in plugin._migrated_sessions


@pytest.mark.asyncio
async def test_truncated_query_is_rechecked_later():
    results = [
        {"memory_id": index, "session_id": "conv-1"}
        for index in range(MIGRATION_QUERY_LIMIT)
    ]
    manager = _Manager(results=results)
    plugin = _plugin(manager)
    unified_origin = "telegram:GroupMessage:conv-1"

    await migrate_session_data_if_needed(plugin, unified_origin, "memories")

    assert unified_origin not in plugin._migrated_sessions
