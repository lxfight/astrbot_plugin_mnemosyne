import asyncio
from types import SimpleNamespace

import pytest
from core.memory_operations import _get_summary_llm_response


class _Provider:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class _HangingProvider:
    def __init__(self):
        self.calls = 0

    async def text_chat(self, **_kwargs):
        self.calls += 1
        await asyncio.sleep(60)


class _Context:
    def __init__(self, fallback=None):
        self.fallback = fallback
        self.requested_provider_ids = []

    def get_using_provider(self, **_kwargs):
        return None

    def get_provider_by_id(self, provider_id):
        self.requested_provider_ids.append(provider_id)
        return self.fallback


@pytest.mark.asyncio
async def test_summary_retries_fallback_provider_after_empty_primary_response():
    primary = _Provider({"completion_text": "  "})
    fallback = _Provider({"completion_text": "fallback summary"})
    context = _Context(fallback)
    plugin = SimpleNamespace(
        provider=primary,
        context=context,
        config={
            "summary_fallback_provider_id": "fallback-provider",
            "use_summary_time_anchor": False,
            "summary_speaker_mapping_prompt": "",
        },
    )

    response = await _get_summary_llm_response(
        plugin,
        "conversation",
        session_id="session-1",
    )

    assert response == {"completion_text": "fallback summary"}
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1
    assert context.requested_provider_ids == ["fallback-provider"]


@pytest.mark.asyncio
async def test_summary_retries_fallback_provider_after_primary_error():
    primary = _Provider(error=RuntimeError("primary unavailable"))
    fallback = _Provider({"completion_text": "fallback summary"})
    plugin = SimpleNamespace(
        provider=primary,
        context=_Context(fallback),
        config={
            "summary_fallback_provider_id": "fallback-provider",
            "use_summary_time_anchor": False,
            "summary_speaker_mapping_prompt": "",
        },
    )

    response = await _get_summary_llm_response(
        plugin,
        "conversation",
        session_id="session-1",
    )

    assert response == {"completion_text": "fallback summary"}
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_summary_retries_fallback_provider_after_primary_timeout():
    primary = _HangingProvider()
    fallback = _Provider({"completion_text": "fallback summary"})
    plugin = SimpleNamespace(
        provider=primary,
        context=_Context(fallback),
        config={
            "summary_fallback_provider_id": "fallback-provider",
            "summary_request_timeout_seconds": 0.01,
            "use_summary_time_anchor": False,
            "summary_speaker_mapping_prompt": "",
        },
    )

    response = await _get_summary_llm_response(
        plugin,
        "conversation",
        session_id="session-1",
    )

    assert response == {"completion_text": "fallback summary"}
    assert primary.calls == 1
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_summary_does_not_call_fallback_after_successful_primary_response():
    primary = _Provider({"completion_text": "primary summary"})
    fallback = _Provider({"completion_text": "fallback summary"})
    plugin = SimpleNamespace(
        provider=primary,
        context=_Context(fallback),
        config={
            "summary_fallback_provider_id": "fallback-provider",
            "use_summary_time_anchor": False,
            "summary_speaker_mapping_prompt": "",
        },
    )

    response = await _get_summary_llm_response(
        plugin,
        "conversation",
        session_id="session-1",
    )

    assert response == {"completion_text": "primary summary"}
    assert len(primary.calls) == 1
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_summary_does_not_retry_same_provider_instance():
    provider = _Provider({"completion_text": "  "})
    plugin = SimpleNamespace(
        provider=provider,
        context=_Context(provider),
        config={
            "summary_fallback_provider_id": "same-provider",
            "use_summary_time_anchor": False,
            "summary_speaker_mapping_prompt": "",
        },
    )

    response = await _get_summary_llm_response(
        plugin,
        "conversation",
        session_id="session-1",
    )

    assert response is None
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_summary_speaker_mapping_renders_conversation_identity():
    primary = _Provider({"completion_text": "summary"})
    plugin = SimpleNamespace(
        provider=primary,
        context=_Context(),
        config={
            "use_summary_time_anchor": False,
            "summary_speaker_mapping_prompt": (
                "persona={persona_id}; session={session_id}; "
                "sender={sender_name}/{sender_id}"
            ),
        },
    )
    history = [
        {
            "role": "user",
            "content": "[Alice(user-42)]: hello",
            "metadata": {"speaker_id": "user-42"},
        }
    ]

    await _get_summary_llm_response(
        plugin,
        "conversation",
        persona_id="persona-7",
        session_id="session-1",
        context_history=history,
    )

    contexts = primary.calls[0]["contexts"]
    assert contexts[-1] == {
        "role": "system",
        "content": (
            "persona=persona-7; session=session-1; sender=Alice/user-42"
        ),
    }
