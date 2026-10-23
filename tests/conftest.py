from __future__ import annotations

import sys
import types
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = PLUGIN_ROOT.parent

for path in (PLUGIN_ROOT, PLUGINS_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _ensure_astrbot_test_stubs() -> None:
    try:
        import astrbot.api.star  # noqa: F401
        import astrbot.core.log  # noqa: F401
        return
    except ImportError:
        pass

    astrbot = sys.modules.get("astrbot") or types.ModuleType("astrbot")
    astrbot_api = sys.modules.get("astrbot.api") or types.ModuleType("astrbot.api")
    astrbot_api_event = sys.modules.get("astrbot.api.event") or types.ModuleType(
        "astrbot.api.event"
    )
    astrbot_api_provider = sys.modules.get("astrbot.api.provider") or types.ModuleType(
        "astrbot.api.provider"
    )
    astrbot_api_star = sys.modules.get("astrbot.api.star") or types.ModuleType(
        "astrbot.api.star"
    )
    astrbot_core = sys.modules.get("astrbot.core") or types.ModuleType("astrbot.core")
    astrbot_core_log = sys.modules.get("astrbot.core.log") or types.ModuleType(
        "astrbot.core.log"
    )
    astrbot_core_provider = (
        sys.modules.get("astrbot.core.provider")
        or types.ModuleType("astrbot.core.provider")
    )
    astrbot_core_provider_provider = (
        sys.modules.get("astrbot.core.provider.provider")
        or types.ModuleType("astrbot.core.provider.provider")
    )

    class _Logger:
        def debug(self, *_args, **_kwargs):
            return None

        def info(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

        def critical(self, *_args, **_kwargs):
            return None

    class _LogManager:
        @staticmethod
        def GetLogger(*_args, **_kwargs):
            return _Logger()

    class _AstrBotConfig(dict):
        pass

    class _AstrMessageEvent:
        pass

    class _Context:
        pass

    class _Star:
        pass

    class _EmbeddingProvider:
        pass

    class _ProviderRequest:
        pass

    class _LLMResponse:
        pass

    class _StarTools:
        pass

    def _identity_decorator(*_args, **_kwargs):
        def _decorate(target):
            return target

        return _decorate

    class _CommandGroup:
        def __init__(self, target):
            self._target = target

        def __call__(self, *args, **kwargs):
            return self._target(*args, **kwargs)

        def command(self, *_args, **_kwargs):
            return _identity_decorator

    def _command_group_decorator(*_args, **_kwargs):
        def _decorate(target):
            return _CommandGroup(target)

        return _decorate

    class _Filter:
        class PermissionType:
            ADMIN = "admin"
            MEMBER = "member"

        on_astrbot_loaded = staticmethod(_identity_decorator)
        on_llm_request = staticmethod(_identity_decorator)
        on_llm_response = staticmethod(_identity_decorator)
        llm_tool = staticmethod(_identity_decorator)
        command_group = staticmethod(_command_group_decorator)
        permission_type = staticmethod(_identity_decorator)

    astrbot_api.AstrBotConfig = getattr(
        astrbot_api, "AstrBotConfig", _AstrBotConfig
    )
    astrbot_api.logger = getattr(astrbot_api, "logger", _Logger())
    astrbot_api_event.AstrMessageEvent = getattr(
        astrbot_api_event, "AstrMessageEvent", _AstrMessageEvent
    )
    astrbot_api_event.filter = getattr(astrbot_api_event, "filter", _Filter())
    astrbot_api_provider.ProviderRequest = getattr(
        astrbot_api_provider, "ProviderRequest", _ProviderRequest
    )
    astrbot_api_provider.LLMResponse = getattr(
        astrbot_api_provider, "LLMResponse", _LLMResponse
    )
    astrbot_api_star.Context = getattr(astrbot_api_star, "Context", _Context)
    astrbot_api_star.Star = getattr(astrbot_api_star, "Star", _Star)
    astrbot_api_star.register = getattr(
        astrbot_api_star, "register", _identity_decorator
    )
    astrbot_api_star.StarTools = getattr(astrbot_api_star, "StarTools", _StarTools)
    astrbot_core_log.LogManager = getattr(astrbot_core_log, "LogManager", _LogManager)
    astrbot_core_provider_provider.EmbeddingProvider = getattr(
        astrbot_core_provider_provider, "EmbeddingProvider", _EmbeddingProvider
    )

    astrbot.api = astrbot_api
    astrbot.core = astrbot_core
    astrbot_api.event = astrbot_api_event
    astrbot_api.provider = astrbot_api_provider
    astrbot_api.star = astrbot_api_star
    astrbot_core.log = astrbot_core_log
    astrbot_core.provider = astrbot_core_provider
    astrbot_core_provider.provider = astrbot_core_provider_provider

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = astrbot_api
    sys.modules["astrbot.api.event"] = astrbot_api_event
    sys.modules["astrbot.api.provider"] = astrbot_api_provider
    sys.modules["astrbot.api.star"] = astrbot_api_star
    sys.modules["astrbot.core"] = astrbot_core
    sys.modules["astrbot.core.log"] = astrbot_core_log
    sys.modules["astrbot.core.provider"] = astrbot_core_provider
    sys.modules["astrbot.core.provider.provider"] = astrbot_core_provider_provider


_ensure_astrbot_test_stubs()
