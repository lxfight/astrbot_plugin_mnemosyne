import asyncio
from types import SimpleNamespace

import core.memory_operations as memory_operations
import pytest
from core.memory_operations import (
    _check_and_trigger_summary,
    _submit_summary_task,
)
from memory_manager.context_manager import ConversationContextManager


class _Counter:
    def __init__(self, count: int = 0):
        self.count = count
        self.reset_calls = 0
        self.restored_values: list[int] = []

    def adjust_counter_if_necessary(self, *_args) -> bool:
        return True

    def get_counter(self, _session_id: str) -> int:
        return self.count

    def reset_counter(self, _session_id: str) -> None:
        self.reset_calls += 1
        self.count = 0

    def restore_counter(self, _session_id: str, value: int) -> None:
        self.restored_values.append(value)
        self.count = value


def _make_plugin(counter: _Counter, concurrency: int = 2):
    return SimpleNamespace(
        config={"num_pairs": 1, "summary_max_concurrency": concurrency},
        msg_counter=counter,
        context_manager=ConversationContextManager(),
        _summary_tasks={},
        _summary_semaphore=None,
    )


def _history() -> list[dict]:
    return [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    ]


async def _drain_tasks(tasks: list[asyncio.Task]) -> None:
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_same_session_cannot_submit_overlapping_summary(monkeypatch):
    counter = _Counter(count=2)
    plugin = _make_plugin(counter)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def slow_summary(*_args, **_kwargs) -> bool:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return True

    monkeypatch.setattr(memory_operations, "handle_summary_long_memory", slow_summary)

    await _check_and_trigger_summary(plugin, "session-1", _history(), None)
    await started.wait()
    task = plugin._summary_tasks["session-1"]

    counter.count = 2
    await _check_and_trigger_summary(plugin, "session-1", _history(), None)

    assert calls == 1
    assert counter.reset_calls == 1

    release.set()
    await _drain_tasks([task])


@pytest.mark.asyncio
async def test_summary_tasks_respect_global_concurrency(monkeypatch):
    first_counter = _Counter(count=2)
    second_counter = _Counter(count=2)
    plugin = _make_plugin(first_counter, concurrency=1)
    plugin.msg_counter = first_counter
    started: list[str] = []
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def controlled_summary(_plugin, _persona, session_id, *_args, **_kwargs):
        started.append(session_id)
        if session_id == "session-1":
            await release_first.wait()
        else:
            second_started.set()
        return True

    monkeypatch.setattr(
        memory_operations, "handle_summary_long_memory", controlled_summary
    )

    await _check_and_trigger_summary(plugin, "session-1", _history(), None)
    first_task = plugin._summary_tasks["session-1"]
    plugin.msg_counter = second_counter
    await _check_and_trigger_summary(plugin, "session-2", _history(), None)
    second_task = plugin._summary_tasks["session-2"]

    await asyncio.sleep(0.05)
    assert started == ["session-1"]
    assert not second_started.is_set()

    release_first.set()
    await asyncio.wait_for(second_started.wait(), timeout=1)
    await _drain_tasks([first_task, second_task])


@pytest.mark.asyncio
async def test_failed_summary_preserves_messages_arrived_during_task(monkeypatch):
    counter = _Counter(count=4)
    plugin = _make_plugin(counter)

    async def failed_summary(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(memory_operations, "handle_summary_long_memory", failed_summary)

    submitted = _submit_summary_task(
        plugin,
        "session-1",
        None,
        "memory text",
        _history(),
        set(),
        pre_summary_count=4,
    )
    assert submitted
    task = plugin._summary_tasks["session-1"]

    counter.count = 0
    counter.count += 2
    await task
    await asyncio.sleep(0)

    assert counter.restored_values == [6]
    assert counter.count == 6


@pytest.mark.asyncio
async def test_successful_summary_updates_completion_time(monkeypatch):
    counter = _Counter(count=2)
    plugin = _make_plugin(counter)
    plugin.context_manager.init_conv("session-1", [], persona_id=None)
    plugin.context_manager.conversations["session-1"]["last_summary_time"] = 1.0

    async def successful_summary(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(
        memory_operations, "handle_summary_long_memory", successful_summary
    )

    submitted = _submit_summary_task(
        plugin,
        "session-1",
        None,
        "memory text",
        _history(),
        set(),
        pre_summary_count=2,
    )
    assert submitted
    await plugin._summary_tasks["session-1"]
    await asyncio.sleep(0)

    assert plugin.context_manager.get_summary_time("session-1") > 1.0
