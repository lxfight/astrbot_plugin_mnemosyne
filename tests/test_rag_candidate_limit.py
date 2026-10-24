"""RAG 候选数测试。"""

from types import SimpleNamespace

import pytest

from admin_panel.services.monitoring_service import MetricsCollector
from core.memory_operations import _perform_vector_db_search


class _SearchVectorDB:
    def __init__(self):
        self.top_k = None

    def search(self, **kwargs):
        self.top_k = kwargs["top_k"]
        return []


@pytest.mark.asyncio
async def test_empty_query_does_not_expand_vector_candidates():
    vector_db = _SearchVectorDB()
    plugin = SimpleNamespace(
        config={},
        collection_name="memory_collection",
        vector_db=vector_db,
        search_params={},
        output_fields_for_query=[],
        metrics_collector=MetricsCollector(),
    )

    result = await _perform_vector_db_search(
        plugin,
        [0.1, 0.2],
        session_id=None,
        persona_id=None,
        query_text="",
        sender_id=None,
    )

    assert result is None
    assert vector_db.top_k == 3
