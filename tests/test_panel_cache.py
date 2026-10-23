"""管理面板短期缓存测试。"""

from types import SimpleNamespace

import pytest

from admin_panel.services.monitoring_service import MonitoringService


class _CountVectorDB:
    def __init__(self):
        self.query_calls = 0

    def is_connected(self):
        return True

    def list_collections(self):
        return ["memory_collection"]

    def has_collection(self, _collection_name):
        return True

    def query(self, _collection_name, **_kwargs):
        self.query_calls += 1
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

    first = await service.get_resource_usage()
    second = await service.get_resource_usage()

    assert first.vector_db_total_records == 2
    assert second is first
    assert plugin.vector_db.query_calls == 1
