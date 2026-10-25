"""Native record-count behavior for optional vector database adapters."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from memory_manager.vector_db.qdrant_adapter import QdrantVectorDB


def test_qdrant_count_uses_exact_native_count():
    adapter = QdrantVectorDB()
    adapter._is_connected = True
    adapter._client = MagicMock()
    adapter._client.count.return_value = SimpleNamespace(count=17)

    count = adapter.count(
        "memory_collection", "session_id == 'session-1'"
    )

    assert count == 17
    call = adapter._client.count.call_args.kwargs
    assert call["collection_name"] == "memory_collection"
    assert call["exact"] is True
    assert call["count_filter"] is not None


def test_qdrant_count_without_filters_passes_empty_filter():
    adapter = QdrantVectorDB()
    adapter._is_connected = True
    adapter._client = MagicMock()
    adapter._client.count.return_value = SimpleNamespace(count=9)

    assert adapter.count("memory_collection") == 9

    call = adapter._client.count.call_args.kwargs
    assert call["count_filter"] is None
    assert call["exact"] is True
