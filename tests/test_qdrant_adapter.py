from types import SimpleNamespace
from unittest.mock import MagicMock

from memory_manager.vector_db.qdrant_adapter import QdrantVectorDB
from memory_manager.vector_db_base import VectorDatabase


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


def test_default_query_page_advances_integer_cursor() -> None:
    adapter = MagicMock()
    adapter.query.side_effect = [
        [{"id": "id-1"}, {"id": "id-2"}],
        [{"id": "id-3"}],
    ]

    first_page, cursor = VectorDatabase.query_page(
        adapter,
        "memory_collection",
        None,
        ["id"],
        limit=2,
    )
    second_page, next_cursor = VectorDatabase.query_page(
        adapter,
        "memory_collection",
        None,
        ["id"],
        limit=2,
        cursor=cursor,
    )

    assert first_page == [{"id": "id-1"}, {"id": "id-2"}]
    assert cursor == 2
    assert second_page == [{"id": "id-3"}]
    assert next_cursor is None
    assert adapter.query.call_args_list[0].kwargs["offset"] == 0
    assert adapter.query.call_args_list[1].kwargs["offset"] == 2


def test_query_page_uses_scroll_cursor() -> None:
    adapter = _connected_adapter()
    adapter._client.scroll.return_value = (
        [SimpleNamespace(id="id-1", payload={"content": "first"})],
        "next-cursor",
    )
    expected_filter = object()
    adapter._parse_filters = MagicMock(return_value=expected_filter)

    records, next_cursor = adapter.query_page(
        "memory_collection",
        "session_id == 'session-1'",
        ["content"],
        limit=2,
        cursor="cursor-1",
    )

    assert records == [{"id": "id-1", "content": "first"}]
    assert next_cursor == "next-cursor"
    call = adapter._client.scroll.call_args.kwargs
    assert call["collection_name"] == "memory_collection"
    assert call["scroll_filter"] is expected_filter
    assert call["limit"] == 2
    assert call["offset"] == "cursor-1"
    adapter._parse_filters.assert_called_once_with("session_id == 'session-1'")


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
