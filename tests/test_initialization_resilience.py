"""回归测试：初始化步骤的失败分级（issue #152）。

config_check 是非关键校验，失败不应中断整个插件初始化；
config_schema 产出后续步骤依赖的状态，失败仍然终止初始化。
"""

import pytest
from astrbot_plugin_mnemosyne.core import initialization
from astrbot_plugin_mnemosyne.main import Mnemosyne


class _ReadyFlag:
    def __init__(self):
        self.is_set = False

    def set(self):
        self.is_set = True

    def clear(self):
        self.is_set = False


def _make_plugin_stub():
    """构造 _initialize_plugin_async 所需的最小插件桩。"""
    return type(
        "_PluginStub",
        (),
        {
            "config": {},
            "context": None,
            "vector_db": None,
            "milvus_manager": None,
            "msg_counter": None,
            "context_manager": None,
            "_embedding_provider_ready": False,
            "_vector_db_ready": _ReadyFlag(),
            "_initialized_components": [],
            "_initialization_successful": False,
            "_are_providers_initialized": lambda self: False,
            "_start_post_load_tasks": lambda self: None,
            "_cleanup_partial_initialization": lambda self: setattr(
                self, "_cleanup_called", True
            ),
        },
    )()


def _record_step(reached_steps: list[str], name: str):
    def _step(_plugin, *_args, **_kwargs):
        reached_steps.append(name)

    return _step


@pytest.mark.asyncio
async def test_config_check_failure_does_not_abort_initialization(monkeypatch):
    """config_check 失败只降级，后续初始化步骤必须继续执行。"""
    stub = _make_plugin_stub()
    reached_steps: list[str] = []

    def _raise_config_check(_plugin):
        raise ValueError("模拟上游配置键缺失")

    monkeypatch.setattr(initialization, "initialize_config_check", _raise_config_check)
    monkeypatch.setattr(
        initialization,
        "initialize_config_and_schema",
        _record_step(reached_steps, "schema"),
    )
    monkeypatch.setattr(
        initialization,
        "initialize_components",
        _record_step(reached_steps, "components"),
    )
    monkeypatch.setattr(
        initialization,
        "initialize_vector_db",
        _record_step(reached_steps, "vector_db"),
    )

    await Mnemosyne._initialize_plugin_async(stub)

    assert stub._initialization_successful is True
    assert "config_check" not in stub._initialized_components
    assert "config_schema" in stub._initialized_components
    assert set(reached_steps) == {"schema", "components", "vector_db"}


@pytest.mark.asyncio
async def test_config_schema_failure_still_aborts_initialization(monkeypatch):
    """config_schema 产出后续步骤依赖的状态，失败必须保持致命。"""
    stub = _make_plugin_stub()

    def _noop(_plugin):
        return None

    def _raise_schema(_plugin):
        raise RuntimeError("schema 初始化失败")

    monkeypatch.setattr(initialization, "initialize_config_check", _noop)
    monkeypatch.setattr(initialization, "initialize_config_and_schema", _raise_schema)

    with pytest.raises(RuntimeError):
        await Mnemosyne._initialize_plugin_async(stub)

    assert stub._initialization_successful is False
    assert getattr(stub, "_cleanup_called", False) is True


@pytest.mark.asyncio
async def test_config_check_passes_and_component_recorded(monkeypatch):
    """config_check 正常时行为不变，组件照常登记。"""
    stub = _make_plugin_stub()

    def _noop(_plugin):
        return None

    monkeypatch.setattr(initialization, "initialize_config_check", _noop)
    monkeypatch.setattr(initialization, "initialize_config_and_schema", _noop)
    monkeypatch.setattr(initialization, "initialize_components", _noop)
    monkeypatch.setattr(initialization, "initialize_vector_db", _noop)

    await Mnemosyne._initialize_plugin_async(stub)

    assert "config_check" in stub._initialized_components
    assert stub._initialization_successful is True
