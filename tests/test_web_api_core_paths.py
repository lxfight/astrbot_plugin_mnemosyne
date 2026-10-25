from __future__ import annotations

from datetime import datetime

import pytest
from quart import Quart

from astrbot_plugin_mnemosyne.admin_panel.models.memory import (
    MemorySearchRequest,
    MemorySearchResponse,
)
from astrbot_plugin_mnemosyne.web_api import MnemosyneWebApi


class _Context:
    def __init__(self, app: Quart) -> None:
        self.app = app

    def register_web_api(self, route, handler, methods, _description) -> None:
        self.app.add_url_rule(
            route,
            endpoint=handler.__name__,
            view_func=handler,
            methods=methods,
        )


class _Plugin:
    def __init__(self, app: Quart) -> None:
        self.config = {"authentication": {"password": "secret"}, "top_k": 5}
        self.context = _Context(app)
        self.save_count = 0

    def save_config(self) -> None:
        self.save_count += 1


class _MemoryService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def search_memories(self, request: MemorySearchRequest):
        self.calls.append(("search", request))
        return MemorySearchResponse(
            records=[],
            total_count=0,
            page=request.offset // request.limit + 1,
            page_size=request.limit,
            has_more=False,
        )

    async def batch_delete_memories(self, memory_ids: list[str]) -> int:
        self.calls.append(("batch_delete", memory_ids))
        return len(memory_ids)

    async def update_memory(self, memory_id: str, content: str):
        self.calls.append(("update", memory_id, content))
        return {"memory_id": memory_id, "content": content}

    async def export_memories(self, **filters):
        self.calls.append(("export", filters))
        return "memory_id,content\nmem-1,hello\n"

    async def vector_search(self, query: str, limit: int):
        self.calls.append(("vector_search", query, limit))
        return [{"memory_id": "mem-1", "content": query}]


def _create_app():
    app = Quart(__name__)
    plugin = _Plugin(app)
    api = MnemosyneWebApi(plugin)
    memory_service = _MemoryService()
    api.memory_service = memory_service
    api.register_routes()
    return app, plugin, memory_service


@pytest.mark.asyncio
async def test_search_memories_bounds_pagination_and_parses_dates() -> None:
    app, _, memory_service = _create_app()
    client = app.test_client()

    response = await client.get(
        "/astrbot_plugin_mnemosyne/memories/search",
        query_string={
            "session_id": "session-1",
            "persona_id": "Alice",
            "limit": "500",
            "offset": "-8",
            "start_date": "2026-01-02T03:04:05",
        },
    )

    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["pagination"]["page_size"] == 100
    request = memory_service.calls[0][1]
    assert request.session_id == "session-1"
    assert request.persona_id == "Alice"
    assert request.limit == 100
    assert request.offset == 0
    assert request.start_date == datetime(2026, 1, 2, 3, 4, 5)


@pytest.mark.asyncio
async def test_search_memories_rejects_blank_session_id() -> None:
    app, _, memory_service = _create_app()
    client = app.test_client()

    response = await client.get(
        "/astrbot_plugin_mnemosyne/memories/search",
        query_string={"session_id": "   "},
    )

    payload = await response.get_json()
    assert payload == {"status": "error", "message": "session_id 格式无效"}
    assert memory_service.calls == []


@pytest.mark.asyncio
async def test_batch_delete_delegates_validated_ids() -> None:
    app, _, memory_service = _create_app()
    client = app.test_client()

    response = await client.post(
        "/astrbot_plugin_mnemosyne/memories/delete",
        json={"memory_ids": ["mem-1", "mem-2"]},
    )

    assert await response.get_json() == {"deleted_count": 2}
    assert memory_service.calls == [("batch_delete", ["mem-1", "mem-2"])]


@pytest.mark.asyncio
async def test_update_memory_delegates_content() -> None:
    app, _, memory_service = _create_app()
    client = app.test_client()

    response = await client.post(
        "/astrbot_plugin_mnemosyne/memories/mem-1/update",
        json={"content": "updated content"},
    )

    payload = await response.get_json()
    assert payload["updated"] is True
    assert payload["record"]["content"] == "updated content"
    assert memory_service.calls == [("update", "mem-1", "updated content")]


@pytest.mark.asyncio
async def test_export_memories_returns_attachment_with_filters() -> None:
    app, _, memory_service = _create_app()
    client = app.test_client()

    response = await client.get(
        "/astrbot_plugin_mnemosyne/memories/export",
        query_string={
            "format": "csv",
            "session_id": "session-1",
            "start_date": "2026-01-01T00:00:00",
        },
    )

    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.headers["Content-Disposition"].endswith('.csv"')
    assert b"mem-1,hello" in await response.get_data()
    _, filters = memory_service.calls[0]
    assert filters["format"] == "csv"
    assert filters["session_id"] == "session-1"
    assert filters["start_date"] == datetime(2026, 1, 1)
    assert filters["end_date"] is None


@pytest.mark.asyncio
async def test_config_endpoints_hide_and_preserve_sensitive_values() -> None:
    app, plugin, _ = _create_app()
    client = app.test_client()

    get_response = await client.get("/astrbot_plugin_mnemosyne/config")
    assert await get_response.get_json() == {"top_k": 5}

    post_response = await client.post(
        "/astrbot_plugin_mnemosyne/config",
        json={"top_k": 8, "authentication": {"password": "replaced"}},
    )

    assert await post_response.get_json() == {"saved": True}
    assert plugin.config["top_k"] == 8
    assert plugin.config["authentication"] == {"password": "secret"}
    assert plugin.save_count == 1


@pytest.mark.asyncio
async def test_vector_search_clamps_limit() -> None:
    app, _, memory_service = _create_app()
    client = app.test_client()

    response = await client.post(
        "/astrbot_plugin_mnemosyne/memories/vector-search",
        json={"query": "北京", "limit": 500},
    )

    assert await response.get_json() == {
        "records": [{"memory_id": "mem-1", "content": "北京"}],
        "total_count": 1,
    }
    assert memory_service.calls == [("vector_search", "北京", 100)]
