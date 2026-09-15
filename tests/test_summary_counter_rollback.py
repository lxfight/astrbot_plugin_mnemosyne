"""回归测试：后台总结失败时回滚消息计数器（issue #150）。

总结任务失败（返回 False、抛异常或被取消）时，之前立即执行的
reset_counter 应被回滚，使会话在下一轮对话重新触发总结，
避免该轮记忆被静默丢弃。
"""

import asyncio
from types import SimpleNamespace

import core.memory_operations as memory_operations
import pytest
from core.memory_operations import _check_and_trigger_summary

_NUM_PAIRS = 2
_THRESHOLD = _NUM_PAIRS * 2


class _StubCounter:
    """模拟 MessageCounter，记录 reset/restore 调用。"""

    def __init__(self, count: int):
        self.count = count
        self.reset_calls = 0
        self.restored_values: list[int] = []

    def adjust_counter_if_necessary(self, session_id, context_history) -> bool:
        return True

    def get_counter(self, session_id) -> int:
        return self.count

    def reset_counter(self, session_id):
        self.reset_calls += 1
        self.count = 0

    def restore_counter(self, session_id, value: int):
        self.restored_values.append(value)
        self.count = value


def _make_history() -> list[dict]:
    return [
        {"role": "user", "content": "user message one"},
        {"role": "assistant", "content": "assistant reply one"},
        {"role": "user", "content": "user message two"},
        {"role": "assistant", "content": "assistant reply two"},
    ]


def _make_plugin(counter: _StubCounter):
    return SimpleNamespace(config={"num_pairs": _NUM_PAIRS}, msg_counter=counter)


async def _wait_background_task() -> None:
    # 等待 create_task 创建的后台总结任务及其 done callback 执行完毕。
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_summary_false_result_restores_counter(monkeypatch):
    counter = _StubCounter(count=_THRESHOLD)
    plugin = _make_plugin(counter)

    async def _fail_summary(*_args, **_kwargs) -> bool:
        return False

    monkeypatch.setattr(memory_operations, "handle_summary_long_memory", _fail_summary)

    await _check_and_trigger_summary(
        plugin, "session-1", _make_history(), persona_id=None
    )
    await _wait_background_task()

    # 提交任务时计数器被重置，失败后必须回滚以便下一轮重试。
    assert counter.reset_calls == 1
    assert counter.restored_values == [_THRESHOLD]
    assert counter.count == _THRESHOLD


@pytest.mark.asyncio
async def test_summary_exception_restores_counter(monkeypatch):
    counter = _StubCounter(count=_THRESHOLD)
    plugin = _make_plugin(counter)

    async def _raise_summary(*_args, **_kwargs):
        raise RuntimeError("LLM connection error")

    monkeypatch.setattr(memory_operations, "handle_summary_long_memory", _raise_summary)

    await _check_and_trigger_summary(
        plugin, "session-1", _make_history(), persona_id=None
    )
    await _wait_background_task()

    assert counter.reset_calls == 1
    assert counter.restored_values == [_THRESHOLD]
    assert counter.count == _THRESHOLD


@pytest.mark.asyncio
async def test_summary_success_keeps_counter_reset(monkeypatch):
    counter = _StubCounter(count=_THRESHOLD)
    plugin = _make_plugin(counter)

    async def _ok_summary(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(memory_operations, "handle_summary_long_memory", _ok_summary)

    await _check_and_trigger_summary(
        plugin, "session-1", _make_history(), persona_id=None
    )
    await _wait_background_task()

    # 成功时保持重置，不回滚。
    assert counter.reset_calls == 1
    assert counter.restored_values == []
    assert counter.count == 0


@pytest.mark.asyncio
async def test_summary_cancelled_restores_counter(monkeypatch):
    counter = _StubCounter(count=_THRESHOLD)
    plugin = _make_plugin(counter)

    async def _cancelled_summary(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        memory_operations, "handle_summary_long_memory", _cancelled_summary
    )

    await _check_and_trigger_summary(
        plugin, "session-1", _make_history(), persona_id=None
    )
    await _wait_background_task()

    assert counter.reset_calls == 1
    assert counter.restored_values == [_THRESHOLD]
    assert counter.count == _THRESHOLD
