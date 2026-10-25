"""管理面板短期缓存测试。"""

import threading
from types import SimpleNamespace

import pytest

from admin_panel.services.monitoring_service import MonitoringService


class _CountVectorDB:
    def __init__(self):
        self.query_calls = 0
        self.operation_thread_ids = []

    def is_connected(self):
        return True

    def list_collections(self):
        self.operation_thread_ids.append(threading.get_ident())
        return ["memory_collection"]

    def has_collection(self, _collection_name):
        return True

    def query(self, _collection_name, **_kwargs):
        self.query_calls += 1
        self.operation_thread_ids.append(threading.get_ident())
        return [{"memory_id": "1"}, {"memory_id": "2"}]


@pytest.mark.asyncio
async def test_resource_usage_reuses_short_ttl_cache():
    plugin = SimpleNamespace(
        vector_db=_CountVectorDB(),
        collection_name="memory_collection",
        msg_counter=None,
        context_manager=None,
    )
    service = MonitoringService(plugin)
    event_loop_thread = threading.get_ident()

    first = await service.get_resource_usage()
    second = await service.get_resource_usage()

    assert first.vector_db_total_records == 2
    assert second is first
    assert plugin.vector_db.query_calls == 1
    assert plugin.vector_db.operation_thread_ids
    assert all(
        thread_id != event_loop_thread
        for thread_id in plugin.vector_db.operation_thread_ids
    )
