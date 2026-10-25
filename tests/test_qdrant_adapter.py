from types import SimpleNamespace
from unittest.mock import MagicMock

from memory_manager.vector_db.qdrant_adapter import QdrantVectorDB


def _connected_adapter() -> QdrantVectorDB:
    adapter = QdrantVectorDB()
    adapter._client = MagicMock()
    adapter._is_connected = True
    return adapter


def test_query_returns_requested_offset_window() -> None:
    adapter = _connected_adapter()
    points = [
        SimpleNamespace(id=f"id-{index}", payload={"content": f"content-{index}"})
        for index in range(5)
    ]
    adapter._client.scroll.return_value = (points, None)
    expected_filter = object()
    adapter._parse_filters = MagicMock(return_value=expected_filter)

    records = adapter.query(
        "memory_collection",
        "session_id == 'session-1'",
        ["content"],
        limit=2,
        offset=2,
    )

    assert [record["id"] for record in records] == ["id-2", "id-3"]
    call = adapter._client.scroll.call_args.kwargs
    assert call["collection_name"] == "memory_collection"
    assert call["scroll_filter"] is expected_filter
    assert call["limit"] == 4
    assert call["with_payload"] is True
    assert call["with_vectors"] is False


def test_get_by_id_returns_point_payload() -> None:
    adapter = _connected_adapter()
    adapter._client.retrieve.return_value = [
        SimpleNamespace(
            id="point-1",
            payload={"content": "remembered", "session_id": "session-1"},
        )
    ]

    record = adapter.get_by_id("memory_collection", "point-1")

    assert record == {
        "id": "point-1",
        "content": "remembered",
        "session_id": "session-1",
    }
    adapter._client.retrieve.assert_called_once_with(
        collection_name="memory_collection",
        ids=["point-1"],
        with_payload=True,
        with_vectors=False,
    )


def test_get_latest_memory_sorts_by_create_time_and_limits() -> None:
    adapter = _connected_adapter()
    adapter._client.scroll.return_value = (
        [
            SimpleNamespace(id="old", payload={"create_time": 10}),
            SimpleNamespace(id="newest", payload={"create_time": 40}),
            SimpleNamespace(id="middle", payload={"create_time": 20}),
        ],
        None,
    )

    records = adapter.get_latest_memory("memory_collection", limit=2)

    assert [record["id"] for record in records] == ["newest", "middle"]
    assert adapter._client.scroll.call_args.kwargs["limit"] == 4
