"""
Mnemosyne 插件核心记忆操作逻辑
包括 RAG 查询、LLM 响应处理、记忆总结与存储。
"""

import asyncio
import hashlib
import re
import time
from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from pymilvus.exceptions import MilvusException
except ImportError:

    class MilvusException(Exception):
        pass


from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.log import LogManager

from .chatroom_parser import ChatroomContextParser
from .constants import (
    DEFAULT_MILVUS_TIMEOUT,
    DEFAULT_PERSONA_ON_NONE,
    DEFAULT_TOP_K,
    VECTOR_FIELD_NAME,
)
from .security_utils import (
    safe_build_milvus_expression,
    validate_personality_id,
    validate_session_id,
)
from .tools import (
    extract_query_keywords,
    format_context_to_string,
    format_tool_calls_result_to_string,
    pack_memory_content,
    remove_mnemosyne_tags,
    remove_system_content,
    remove_system_mnemosyne_tags,
    resolve_max_prompt_chars,
    split_memory_content_meta,
    strip_memory_meta,
    truncate_for_embedding,
)

# 类型提示，避免循环导入
if TYPE_CHECKING:
    from ..main import Mnemosyne

logger = LogManager.GetLogger(__name__)

USER_RECORDED_EXTRA_KEY = "_mnemosyne_user_recorded"
ASSISTANT_RECORDED_EXTRA_KEY = "_mnemosyne_assistant_recorded"
TOOL_CONTEXT_RECORDED_EXTRA_KEY = "_mnemosyne_tool_context_recorded"
REQUEST_PROCESSED_EXTRA_KEY = "_mnemosyne_request_processed"
TOOL_CONTEXT_MARKER_METADATA_KEY = "_mnemosyne_tool_context_turn_marker"
_MISSING = object()
_TURN_MARKER_TTL_SECONDS = 10 * 60
_TURN_MARKER_MAX_ENTRIES = 4096
_INJECTION_COUNTER_MAX_SESSIONS = 2048
_LAST_USER_TURN_MAX_SESSIONS = 2048
_MAX_RETAINED_TOOL_CONTEXT_MESSAGES = 8
DEFAULT_SUMMARY_SPEAKER_MAPPING_PROMPT = (
    "说话人映射：assistant 表示当前会话正在运行的人格角色"
    "（persona_id={persona_id}），user 表示当前对话用户"
    "（sender_name={sender_name}，sender_id={sender_id}，session_id={session_id}）。"
    "总结中的“我/我的”只能指 assistant 对应的人格角色；"
    "user 发言中的第一人称应改写为用户昵称、用户或其。"
    "除非原始对话或人设明确如此自称，不要把 assistant 称为 AI、助手、bot 或模型。"
)


def _get_vector_db(plugin: "Mnemosyne"):
    """获取当前配置的向量数据库实例。"""
    return getattr(plugin, "vector_db", None)


def _extract_explicit_memory_content(prompt: str) -> str | None:
    """
    识别用户显式“记住”指令，提取需要写入长期记忆的正文。
    """
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    if not text:
        return None

    patterns = [
        r"^\s*记住[:：\s]+(.+)$",
        r"^\s*请记住[:：\s]+(.+)$",
        r"^\s*帮我记住[:：\s]+(.+)$",
        r"^\s*remember(?:\s+this)?[:：\s]+(.+)$",
        r"^\s*please\s+remember[:：\s]+(.+)$",
    ]
    for pattern in patterns:
        matched = re.match(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if matched:
            content = matched.group(1).strip()
            if content:
                return content
    return None


def _get_event_extra(event: AstrMessageEvent, key: str, default: Any = None) -> Any:
    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return default
    try:
        return getter(key, default)
    except TypeError:
        try:
            value = getter(key)
        except Exception:
            return default
        return default if value is _MISSING else value
    except Exception:
        return default


def _set_event_extra(event: AstrMessageEvent, key: str, value: Any) -> None:
    setter = getattr(event, "set_extra", None)
    if not callable(setter):
        return
    try:
        setter(key, value)
    except Exception:
        logger.debug(f"写入事件标记 {key} 失败", exc_info=True)


def _get_turn_marker_store(
    plugin: "Mnemosyne", attr_name: str
) -> OrderedDict[str, float]:
    store = getattr(plugin, attr_name, None)
    if not isinstance(store, OrderedDict):
        converted: OrderedDict[str, float] = OrderedDict()
        if isinstance(store, dict):
            for key, value in store.items():
                if isinstance(key, str) and isinstance(value, (int, float)):
                    converted[key] = float(value)
        store = converted
        setattr(plugin, attr_name, store)
    return store


def _prune_turn_marker_store(store: OrderedDict[str, float]) -> None:
    now = time.monotonic()
    while store:
        oldest_key = next(iter(store))
        oldest_updated_at = store[oldest_key]
        if now - oldest_updated_at <= _TURN_MARKER_TTL_SECONDS:
            break
        store.popitem(last=False)

    while len(store) > _TURN_MARKER_MAX_ENTRIES:
        store.popitem(last=False)


def _warn_empty_turn_marker(plugin: "Mnemosyne", attr_name: str) -> None:
    warned_attrs = getattr(plugin, "_mnemosyne_empty_marker_warning_attrs", None)
    if not isinstance(warned_attrs, set):
        warned_attrs = set()
        plugin._mnemosyne_empty_marker_warning_attrs = warned_attrs
    if attr_name in warned_attrs:
        return
    warned_attrs.add(attr_name)
    logger.warning(f"无法为 {attr_name} 构建稳定 turn marker，已保守跳过本轮记忆处理。")


def _mark_turn_once(plugin: "Mnemosyne", attr_name: str, marker: str) -> bool:
    if not marker:
        _warn_empty_turn_marker(plugin, attr_name)
        return False

    store = _get_turn_marker_store(plugin, attr_name)
    _prune_turn_marker_store(store)
    if marker in store:
        store[marker] = time.monotonic()
        store.move_to_end(marker)
        return False
    store[marker] = time.monotonic()
    _prune_turn_marker_store(store)
    return True


def _has_turn_marker(plugin: "Mnemosyne", attr_name: str, marker: str) -> bool:
    if not marker:
        return False
    store = _get_turn_marker_store(plugin, attr_name)
    _prune_turn_marker_store(store)
    if marker not in store:
        return False
    store[marker] = time.monotonic()
    store.move_to_end(marker)
    return True


def _stringify_marker_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        text = str(value)
    except Exception:
        text = repr(value)
    return text.strip()


def _digest_marker_text(*parts: Any) -> str:
    text_parts = [
        _stringify_marker_value(part) for part in parts if _stringify_marker_value(part)
    ]
    if not text_parts:
        return ""
    payload = "\u241f".join(text_parts)
    return hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()


def _extract_event_message_token(event: AstrMessageEvent) -> str:
    candidate_attrs = [
        "message_id",
        "msg_id",
        "message_uid",
        "id",
        "timestamp",
        "time",
    ]
    for attr in candidate_attrs:
        value = _stringify_marker_value(getattr(event, attr, None))
        if value:
            return f"{attr}={value}"

    for container_attr in ("message_obj", "message", "msg"):
        container = getattr(event, container_attr, None)
        if not container:
            continue
        for attr in candidate_attrs:
            value = _stringify_marker_value(getattr(container, attr, None))
            if value:
                return f"{container_attr}.{attr}={value}"
    return ""


def _extract_event_outline(event: AstrMessageEvent) -> str:
    outline_getter = getattr(event, "get_message_outline", None)
    if callable(outline_getter):
        try:
            outline = outline_getter()
        except Exception:
            outline = ""
        value = _stringify_marker_value(outline)
        if value:
            return value
    return ""


def _build_turn_marker(
    plugin: "Mnemosyne",
    event: AstrMessageEvent,
    *,
    session_id: str | None = None,
    prompt_text: str | None = None,
) -> str:
    session = _stringify_marker_value(session_id) or _stringify_marker_value(
        getattr(event, "unified_msg_origin", "")
    )
    if not session:
        return ""

    sender_id = ""
    sender_getter = getattr(event, "get_sender_id", None)
    if callable(sender_getter):
        try:
            sender_id = _stringify_marker_value(sender_getter())
        except Exception:
            sender_id = ""

    token = _extract_event_message_token(event)
    if token:
        parts = [session]
        if sender_id:
            parts.append(f"sender={sender_id}")
        parts.append(token)
        return "|".join(parts)

    if prompt_text is None:
        prompt_text = _extract_event_outline(event)

    image_urls = getattr(event, "image_urls", None)
    digest = _digest_marker_text(
        prompt_text,
        _extract_event_outline(event),
        image_urls,
        getattr(event, "platform_meta", None),
    )
    if not digest:
        return ""

    parts = [session]
    if sender_id:
        parts.append(f"sender={sender_id}")
    parts.append(f"digest={digest}")
    return "|".join(parts)


def _resolve_response_turn_marker(
    plugin: "Mnemosyne", event: AstrMessageEvent, session_id: str
) -> str:
    event_marker = _build_turn_marker(plugin, event, session_id=session_id)
    if event_marker:
        return event_marker

    # 只有当前响应事件无法构建稳定 marker 时才回退到最近的用户轮次。
    # 如果当前事件有 marker 但未记录过用户消息，必须保留该 marker，让
    # handle_on_llm_resp 的 user_was_recorded=False 分支继续执行总结检查。
    last_turns = _get_last_user_turn_store(plugin)
    last_marker = last_turns.get(session_id, "")
    if last_marker and _has_turn_marker(
        plugin, "_mnemosyne_recorded_user_turns", last_marker
    ):
        last_turns.move_to_end(session_id)
        return last_marker

    return event_marker


def _get_last_user_turn_store(plugin: "Mnemosyne") -> OrderedDict[str, str]:
    store = getattr(plugin, "_mnemosyne_last_user_turn_by_session", None)
    if not isinstance(store, OrderedDict):
        converted: OrderedDict[str, str] = OrderedDict()
        if isinstance(store, dict):
            for session_id, marker in store.items():
                session = _stringify_marker_value(session_id)
                marker_text = _stringify_marker_value(marker)
                if session and marker_text:
                    converted[session] = marker_text
        store = converted
        plugin._mnemosyne_last_user_turn_by_session = store
    while len(store) > _LAST_USER_TURN_MAX_SESSIONS:
        store.popitem(last=False)
    return store


def _remember_last_user_turn(
    plugin: "Mnemosyne", session_id: str, turn_marker: str
) -> None:
    if not session_id or not turn_marker:
        return
    last_turns = _get_last_user_turn_store(plugin)
    last_turns[session_id] = turn_marker
    last_turns.move_to_end(session_id)
    while len(last_turns) > _LAST_USER_TURN_MAX_SESSIONS:
        last_turns.popitem(last=False)


def _summary_should_include_tool_context(plugin: "Mnemosyne") -> bool:
    try:
        return bool(plugin.config.get("include_tool_context_in_summary", False))
    except Exception:
        return False


def _append_tool_context_if_enabled(
    plugin: "Mnemosyne",
    event: AstrMessageEvent,
    session_id: str,
    turn_marker: str,
) -> None:
    if not _summary_should_include_tool_context(plugin):
        return
    tool_context_recorded = _get_event_extra(
        event, TOOL_CONTEXT_RECORDED_EXTRA_KEY, False
    ) or _has_turn_marker(
        plugin,
        "_mnemosyne_recorded_tool_context_turns",
        turn_marker,
    )
    if tool_context_recorded:
        return
    if not plugin.context_manager:
        return

    provider_request = _get_event_extra(event, "provider_request")
    tool_calls_result = getattr(provider_request, "tool_calls_result", None)
    tool_context = format_tool_calls_result_to_string(tool_calls_result)
    if not tool_context.strip():
        return

    plugin.context_manager.add_message(
        session_id,
        "tool",
        tool_context,
        metadata={
            "speaker_id": "tool",
            TOOL_CONTEXT_MARKER_METADATA_KEY: turn_marker,
        },
    )
    _trim_recorded_tool_context(plugin, session_id)
    _set_event_extra(event, TOOL_CONTEXT_RECORDED_EXTRA_KEY, True)
    _mark_turn_once(plugin, "_mnemosyne_recorded_tool_context_turns", turn_marker)
    logger.debug(
        f"已记录工具调用上下文用于记忆总结，session={session_id}, 长度={len(tool_context)}"
    )


def _collect_tool_context_markers(context_history: list[dict] | None) -> set[str]:
    if not isinstance(context_history, list):
        return set()
    markers: set[str] = set()
    for message in context_history:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        metadata = message.get("metadata")
        if not isinstance(metadata, dict):
            continue
        marker = metadata.get(TOOL_CONTEXT_MARKER_METADATA_KEY)
        if isinstance(marker, str) and marker:
            markers.add(marker)
    return markers


def _clear_recorded_tool_context(
    plugin: "Mnemosyne", session_id: str, turn_markers: set[str]
) -> None:
    context_manager = getattr(plugin, "context_manager", None)
    if not context_manager or not turn_markers:
        return

    clear_method = getattr(context_manager, "clear_role_messages_by_metadata", None)
    if not callable(clear_method):
        return

    removed = clear_method(
        session_id,
        "tool",
        TOOL_CONTEXT_MARKER_METADATA_KEY,
        turn_markers,
    )
    if removed:
        logger.debug(f"已清理会话 {session_id} 的 {removed} 条临时 tool 上下文。")


def _trim_recorded_tool_context(plugin: "Mnemosyne", session_id: str) -> None:
    context_manager = getattr(plugin, "context_manager", None)
    if not context_manager:
        return

    trim_method = getattr(context_manager, "trim_role_messages", None)
    if not callable(trim_method):
        return

    removed = trim_method(session_id, "tool", _MAX_RETAINED_TOOL_CONTEXT_MESSAGES)
    if removed:
        logger.debug(f"已裁剪会话 {session_id} 的 {removed} 条旧临时 tool 上下文。")


def _prune_injection_round_counter(plugin: "Mnemosyne") -> None:
    counter = getattr(plugin, "_injection_round_counter", None)
    touched_at = getattr(plugin, "_injection_round_counter_updated_at", None)
    if not isinstance(counter, dict):
        plugin._injection_round_counter = {}
        counter = plugin._injection_round_counter
    if not isinstance(touched_at, dict):
        plugin._injection_round_counter_updated_at = {}
        touched_at = plugin._injection_round_counter_updated_at

    stale_sessions = [
        session_id for session_id in touched_at if session_id not in counter
    ]
    for session_id in stale_sessions:
        touched_at.pop(session_id, None)

    excess = len(counter) - _INJECTION_COUNTER_MAX_SESSIONS
    if excess <= 0:
        return

    oldest_sessions = sorted(
        counter.keys(), key=lambda session_id: touched_at.get(session_id, 0.0)
    )[:excess]
    for session_id in oldest_sessions:
        counter.pop(session_id, None)
        touched_at.pop(session_id, None)


def _resolve_memory_injection_interval(plugin: "Mnemosyne") -> int:
    raw_interval = 1
    try:
        raw_interval = plugin.config.get("memory_injection_interval", 1)
    except Exception:
        raw_interval = 1

    try:
        interval = int(raw_interval)
    except (TypeError, ValueError):
        logger.warning(
            f"memory_injection_interval={raw_interval!r} 无法解析为整数，已回退为 1。"
        )
        return 1

    if interval < 1:
        logger.warning(f"memory_injection_interval={interval} 小于 1，已回退为 1。")
        return 1
    return interval


def _should_inject_memory_this_turn(plugin: "Mnemosyne", session_id: str) -> bool:
    """
    维护每会话注入间隔计数器，返回当前轮是否应执行 RAG 检索与注入。
    计数器有上限裁剪，避免长期运行时无界增长。
    """
    injection_interval = _resolve_memory_injection_interval(plugin)
    if injection_interval <= 1:
        return True

    _prune_injection_round_counter(plugin)
    counter = plugin._injection_round_counter
    touched_at = plugin._injection_round_counter_updated_at
    current = counter.get(session_id, 0) + 1

    if current < injection_interval:
        counter[session_id] = current
        touched_at[session_id] = time.monotonic()
        logger.debug(
            f"间隔注入门控：会话 {session_id} 当前第 {current}/{injection_interval} 轮，"
            f"本轮跳过记忆检索与注入。"
        )
        return False

    # 达到间隔阈值，本轮触发注入并重置计数。
    counter.pop(session_id, None)
    touched_at.pop(session_id, None)
    logger.debug(
        f"间隔注入门控：会话 {session_id} 已达 {injection_interval} 轮，"
        "本轮触发记忆注入。"
    )
    return True


def _collect_participants_from_context(context_history: list[dict] | None) -> list[str]:
    """
    从上下文中提取参与者 ID（仅统计 user 角色）。
    """
    if not isinstance(context_history, list):
        return []

    participants: list[str] = []
    seen: set[str] = set()
    for item in context_history:
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        speaker_id = metadata.get("speaker_id")
        if isinstance(speaker_id, str) and speaker_id.strip():
            normalized = speaker_id.strip()
            if normalized not in seen:
                participants.append(normalized)
                seen.add(normalized)
    return participants


def _extract_sender_field(
    sender_obj: Any,
    keys: tuple[str, ...],
    *,
    allow_non_str: bool,
) -> str:
    if sender_obj is None:
        return ""

    if isinstance(sender_obj, dict):
        for key in keys:
            value = sender_obj.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
            elif allow_non_str and value is not None:
                text = str(value).strip()
                if text:
                    return text
        return ""

    for attr in keys:
        value = getattr(sender_obj, attr, None)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
        elif allow_non_str and value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _extract_sender_name(sender_obj: Any) -> str:
    return _extract_sender_field(
        sender_obj,
        ("nickname", "nick", "name", "card", "remark"),
        allow_non_str=False,
    )


def _extract_sender_id(sender_obj: Any) -> str:
    return _extract_sender_field(
        sender_obj,
        ("user_id", "id", "qq", "uin"),
        allow_non_str=True,
    )


def _fallback_private_sender_id_from_session_id(session_id: str | None) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        return ""

    parts = session_id.split(":", 2)
    if len(parts) != 3:
        return ""

    message_type_raw = parts[1].strip()
    if not message_type_raw:
        return ""

    # 仅接受明确的私聊类型，避免 "NotFriendMessage" 这类误匹配。
    message_type = re.sub(r"[^a-z0-9]", "", message_type_raw.lower())
    if not (
        message_type in {"friend", "friendmessage", "private", "privatemessage"}
        or message_type.startswith("friend")
        or message_type.startswith("private")
    ):
        return ""

    return parts[2].strip()


def _resolve_sender_identity(
    event: AstrMessageEvent,
    session_id: str | None,
) -> tuple[str, str]:
    sender_id = ""
    try:
        if hasattr(event, "get_sender_id"):
            raw_sender_id = event.get_sender_id()
            if raw_sender_id is not None:
                sender_id = str(raw_sender_id).strip()
    except (AttributeError, TypeError, ValueError) as e:
        logger.debug(f"读取 get_sender_id 失败，将继续尝试其他来源: {e}")
        sender_id = ""
    except Exception as e:
        logger.warning(f"读取 get_sender_id 时出现未预期异常，将回退其他来源: {e}")
        sender_id = ""

    message_obj = getattr(event, "message_obj", None)
    message_sender = getattr(message_obj, "sender", None)
    event_sender = getattr(event, "sender", None)

    if not sender_id:
        sender_id = _extract_sender_id(message_sender)
    if not sender_id:
        sender_id = _extract_sender_id(event_sender)
    if not sender_id:
        sender_id = _fallback_private_sender_id_from_session_id(session_id)

    sender_name = _extract_sender_name(message_sender)
    if not sender_name:
        sender_name = _extract_sender_name(event_sender)
    if not sender_name:
        sender_name = "用户"

    return sender_name, sender_id


def _build_identity_prefixed_user_text(
    message_text: Any,
    sender_name: Any,
    sender_id: Any,
) -> str:
    text = message_text if isinstance(message_text, str) else str(message_text)
    normalized_name = sender_name.strip() if isinstance(sender_name, str) else ""
    if not normalized_name:
        normalized_name = "用户"

    normalized_sender_id = str(sender_id).strip() if sender_id is not None else ""
    if normalized_sender_id:
        return f"[{normalized_name}({normalized_sender_id})]: {text}"
    return f"[{normalized_name}]: {text}"


def _build_speaker_metadata(sender_id: Any) -> dict[str, str]:
    normalized_sender_id = str(sender_id).strip() if sender_id is not None else ""
    return {"speaker_id": normalized_sender_id} if normalized_sender_id else {}


def _build_lightweight_graph_metadata(
    summary_text: str,
    context_history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    生成轻量图谱元数据：实体、关系、参与者。
    """
    entities = extract_query_keywords(summary_text, min_token_len=2)[:20]
    relations: list[list[str]] = []
    relation_seen: set[tuple[str, str]] = set()

    # 基于句内共现构建轻量关系边（无额外数据库依赖）。
    sentences = re.split(r"[。！？!?；;\n]+", summary_text)
    for sentence in sentences:
        sentence_entities = extract_query_keywords(sentence, min_token_len=2)[:8]
        n = len(sentence_entities)
        for i in range(n):
            for j in range(i + 1, n):
                a = sentence_entities[i]
                b = sentence_entities[j]
                if a == b:
                    continue
                edge = (a, b) if a < b else (b, a)
                if edge in relation_seen:
                    continue
                relation_seen.add(edge)
                relations.append([edge[0], edge[1]])
                if len(relations) >= 40:
                    break
            if len(relations) >= 40:
                break
        if len(relations) >= 40:
            break

    return {
        "participants": _collect_participants_from_context(context_history),
        "entities": entities,
        "relations": relations,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _expand_graph_keywords(
    base_keywords: list[str], detailed_results: list[dict[str, Any]]
) -> list[str]:
    """
    依据候选记忆携带的 relations 做一次 one-hop 关键词扩展。
    """
    if not base_keywords:
        return []

    expanded: list[str] = []
    seen = set(base_keywords)
    for result in detailed_results:
        meta = result.get("_meta", {})
        if not isinstance(meta, dict):
            continue
        relations = meta.get("relations", [])
        if not isinstance(relations, list):
            continue
        for pair in relations:
            if (
                isinstance(pair, list)
                and len(pair) == 2
                and isinstance(pair[0], str)
                and isinstance(pair[1], str)
            ):
                a = pair[0].strip().lower()
                b = pair[1].strip().lower()
                if not a or not b:
                    continue
                if a in seen and b not in seen:
                    expanded.append(b)
                    seen.add(b)
                elif b in seen and a not in seen:
                    expanded.append(a)
                    seen.add(a)
    return expanded


def _post_process_search_results(
    plugin: "Mnemosyne",
    detailed_results: list[dict[str, Any]],
    query_text: str,
    sender_id: str | None,
) -> list[dict[str, Any]]:
    """
    对向量搜索结果进行后处理：
    1) 参与者过滤（可选）
    2) 关键词/轻量图谱重排（可选）
    """
    if not detailed_results:
        return detailed_results

    prepared: list[dict[str, Any]] = []
    for result in detailed_results:
        if not isinstance(result, dict):
            continue
        content = result.get("content", "")
        pure_content, meta = split_memory_content_meta(content)
        merged = dict(result)
        merged["content"] = pure_content
        merged["_meta"] = meta
        prepared.append(merged)

    # 参与者过滤
    normalized_sender_id = sender_id.strip() if isinstance(sender_id, str) else ""
    if plugin.config.get("use_participant_filtering", False) and normalized_sender_id:
        filtered: list[dict[str, Any]] = []
        for result in prepared:
            meta = result.get("_meta", {})
            participants = (
                meta.get("participants", []) if isinstance(meta, dict) else []
            )
            if not isinstance(participants, list) or not participants:
                # 无参与者信息时不强行过滤，保持兼容旧记录。
                filtered.append(result)
                continue
            normalized = {str(x).strip() for x in participants if str(x).strip()}
            if normalized_sender_id in normalized:
                filtered.append(result)
        if filtered:
            prepared = filtered

    # 关键词 + 图谱扩展重排
    keywords = extract_query_keywords(query_text, min_token_len=2)
    if not keywords:
        return prepared

    use_graph = plugin.config.get("use_lightweight_memory_graph", True)
    expanded = _expand_graph_keywords(keywords, prepared) if use_graph else []
    all_terms = keywords + [term for term in expanded if term not in keywords]

    def _semantic_score(item: dict[str, Any]) -> float:
        distance = item.get("_distance")
        if isinstance(distance, (int, float)):
            # 距离越小越相似，这里转为“分数越大越好”。
            return -float(distance)
        return 0.0

    scored = []
    for item in prepared:
        content = str(item.get("content", ""))
        content_l = content.lower()
        keyword_hits = 0
        for term in all_terms:
            term_l = term.lower()
            if term_l and term_l in content_l:
                keyword_hits += 1
        scored.append((keyword_hits, _semantic_score(item), item))

    if any(hit > 0 for hit, _, _ in scored):
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [item for _, _, item in scored]
    return prepared


async def handle_query_memory(
    plugin: "Mnemosyne", event: AstrMessageEvent, req: ProviderRequest
):
    """
    处理 LLM 请求前的 RAG 检索逻辑。
    检索相关的长期记忆，并将其注入到 ProviderRequest 中。
    """
    # logger = plugin.logger

    # --- 前置检查 ---
    if not await _check_rag_prerequisites(plugin):
        return

    try:
        # --- 获取会话和人格信息 ---
        persona_id = await _get_persona_id(plugin, event)
        # 直接使用 unified_msg_origin 作为 session_id，确保多Bot场景下的记忆隔离
        session_id = event.unified_msg_origin

        # 【新增】触发运行时自动迁移。该迁移逻辑依赖 Milvus 细节，仅在 Milvus 后端启用。
        if (
            plugin.config.get("vector_db_type", "chroma").lower() == "milvus"
            and session_id
            and ":" in session_id
        ):
            # 异步触发迁移，不阻塞查询
            from .migration_utils import migrate_session_data_if_needed

            asyncio.create_task(
                migrate_session_data_if_needed(
                    plugin, session_id, plugin.collection_name
                )
            )

        # M12 修复: 加强 session_id 空值检查，确保类型和内容都有效
        if (
            session_id is None
            or not isinstance(session_id, str)
            or not session_id.strip()
        ):
            logger.error(
                f"无法获取有效的 session_id (值: {session_id}, 类型: {type(session_id).__name__})，跳过记忆查询操作"
            )
            return

        # 检查 context_manager 和 msg_counter 是否可用
        if not plugin.context_manager or not plugin.msg_counter:
            logger.warning("context_manager 或 msg_counter 不可用，跳过记忆查询")
            return

        # 在最早阶段清理 Mnemosyne 标签，避免将带标签/异常结构的 contexts 写入会话历史。
        clean_contexts(plugin, req)

        # 判断是否在历史会话管理器中，如果不在，则进行初始化
        if session_id not in plugin.context_manager.conversations:
            plugin.context_manager.init_conv(session_id, req.contexts, event)

        # 生成供“插件内部记忆/向量化”使用的安全用户文本：
        # - AstrBot 可能在纯图片消息时令 prompt=None，此处用占位符避免报错
        # - 不修改 req.prompt，避免影响实际发给 LLM 的内容
        raw_prompt = req.prompt if isinstance(req.prompt, str) else ""
        safe_user_prompt = raw_prompt
        if not safe_user_prompt.strip() and getattr(req, "image_urls", None):
            safe_user_prompt = "[图片]"

        # 在写入会话历史前先剥离群聊包装，避免把整段 chatroom 模板污染进记忆上下文
        actual_query_raw = ChatroomContextParser.extract_actual_message(
            safe_user_prompt
        )
        if not actual_query_raw.strip() and getattr(req, "image_urls", None):
            actual_query_raw = "[图片]"
        if actual_query_raw != safe_user_prompt:
            logger.debug(
                f"检测到群聊上下文格式，已提取真实消息用于记忆存储与 RAG 搜索 "
                f"(原始: {len(safe_user_prompt)}字符 → 提取: {len(actual_query_raw)}字符)"
            )

        # 防御：极端情况下避免将超长文本写入记忆/embedding
        max_prompt_chars = resolve_max_prompt_chars(plugin.config, default=4000)
        original_query_len = len(actual_query_raw)
        actual_query, query_was_truncated = truncate_for_embedding(
            actual_query_raw,
            max_prompt_chars,
            append_suffix=True,
        )
        if query_was_truncated:
            logger.warning(
                f"用户输入过长 ({original_query_len} chars)，已截断到 {max_prompt_chars} chars。"
            )

        turn_marker = _build_turn_marker(
            plugin,
            event,
            session_id=session_id,
            prompt_text=actual_query,
        )
        if _get_event_extra(
            event, REQUEST_PROCESSED_EXTRA_KEY, False
        ) or not _mark_turn_once(
            plugin, "_mnemosyne_processed_request_turns", turn_marker
        ):
            logger.debug(
                f"会话 {session_id} 当前轮已处理过记忆请求，跳过重复计数与注入。"
            )
            return
        _set_event_extra(event, REQUEST_PROCESSED_EXTRA_KEY, True)

        # 添加用户消息（写入插件上下文管理器）。同一个 AstrBot 事件可能经历多次
        # LLM/tool 循环，用户输入只应计入一次。
        sender_name, sender_id = _resolve_sender_identity(event, session_id)
        user_already_recorded = _get_event_extra(
            event, USER_RECORDED_EXTRA_KEY, False
        ) or _has_turn_marker(plugin, "_mnemosyne_recorded_user_turns", turn_marker)
        if not user_already_recorded:
            memory_store_text = _build_identity_prefixed_user_text(
                actual_query,
                sender_name=sender_name,
                sender_id=sender_id,
            )
            plugin.context_manager.add_message(
                session_id,
                "user",
                memory_store_text,
                metadata=_build_speaker_metadata(sender_id),
            )
            plugin.msg_counter.increment_counter(session_id)
            _set_event_extra(event, USER_RECORDED_EXTRA_KEY, True)
            _mark_turn_once(plugin, "_mnemosyne_recorded_user_turns", turn_marker)
            _remember_last_user_turn(plugin, session_id, turn_marker)
        else:
            logger.debug(f"会话 {session_id} 当前事件用户消息已记录，跳过重复计数。")
            _set_event_extra(event, USER_RECORDED_EXTRA_KEY, True)
            _mark_turn_once(plugin, "_mnemosyne_recorded_user_turns", turn_marker)
            _remember_last_user_turn(plugin, session_id, turn_marker)

        # 支持显式记忆触发：只要用户明确要求“记住”，就不受间隔注入门控影响。
        if plugin.config.get("enable_explicit_memory_capture", False):
            explicit_content = _extract_explicit_memory_content(actual_query)
            if explicit_content:
                try:
                    stored = await store_manual_memory(
                        plugin=plugin,
                        event=event,
                        memory_content=explicit_content,
                        source="explicit_trigger",
                    )
                    if stored:
                        logger.info("已根据显式“记住”触发写入长期记忆。")
                except Exception as e:
                    logger.error(
                        f"显式记忆写入失败，将继续执行后续记忆流程: {e}",
                        exc_info=True,
                    )

        # --- 间隔注入门控 ---
        # “每隔 N 轮对话才触发一次记忆插入”。N<=1 表示每轮都注入（保持原行为）。
        # 该门控仅控制本轮是否执行 RAG 检索与注入，不影响用户消息入库与总结计数。
        # 注意：此处不累计召回历史，触发时仅注入“当前这一轮”检索到的记忆。
        if not _should_inject_memory_this_turn(plugin, session_id):
            return

        # --- RAG 搜索 ---
        detailed_results = []
        try:
            # 1. 向量化用户查询
            # 使用 AstrBot EmbeddingProvider（异步）
            try:
                # 等待 Embedding Provider 就绪
                if (
                    not plugin.embedding_provider
                    and not plugin._embedding_provider_ready
                ):
                    logger.warning("Embedding Provider 不可用，无法执行 RAG 搜索")
                    return

                # 使用 AstrBot EmbeddingProvider 的 embed 方法
                if plugin.embedding_provider:
                    # 使用提取的真实消息进行向量化
                    query_vector = await plugin.embedding_provider.get_embedding(
                        actual_query
                    )
                else:
                    logger.error("Embedding Provider 未正确初始化")
                    return

                if not query_vector:
                    logger.error("无法获取用户查询的 Embedding 向量。")
                    return

            except ConnectionError as e:
                logger.error(f"网络连接错误，无法获取 Embedding: {e}", exc_info=True)
                return
            except ValueError as e:
                logger.error(f"输入参数错误，无法获取 Embedding: {e}", exc_info=True)
                return
            except RuntimeError as e:
                logger.error(f"运行时错误，无法获取 Embedding: {e}", exc_info=True)
                return
            except Exception as e:
                logger.error(f"获取 Embedding 时发生未知错误: {e}", exc_info=True)
                return

            # 2. 执行 Milvus 搜索
            detailed_results = await _perform_milvus_search(
                plugin,
                query_vector,
                session_id,
                persona_id,
                query_text=actual_query,
                sender_id=sender_id,
            )

            # 3. 格式化结果并注入到提示中
            if detailed_results:
                _format_and_inject_memory(plugin, detailed_results, req)

        except Exception as e:
            logger.error(f"处理长期记忆 RAG 查询时发生错误: {e}", exc_info=True)
            return

    except Exception as e:
        logger.error(f"处理 LLM 请求前的记忆查询流程失败: {e}", exc_info=True)


async def handle_on_llm_resp(
    plugin: "Mnemosyne", event: AstrMessageEvent, resp: LLMResponse
):
    """
    处理 LLM 响应后的逻辑。更新计数器。
    """
    if resp.role != "assistant":
        logger.warning("LLM 响应不是助手角色，不进行记录。")
        return

    # 检查是否有 context_manager 和 msg_counter
    if not plugin.context_manager or not plugin.msg_counter:
        logger.warning("context_manager 或 msg_counter 不可用，跳过记忆记录")
        return

    try:
        # 直接使用 unified_msg_origin 作为 session_id
        session_id = event.unified_msg_origin
        if not session_id:
            logger.error("无法获取当前 session_id,无法记录 LLM 响应到Mnemosyne。")
            return
        persona_id = await _get_persona_id(plugin, event)
        turn_marker = _resolve_response_turn_marker(plugin, event, session_id)

        tool_call_names = getattr(resp, "tools_call_name", _MISSING)
        if tool_call_names is None:
            tool_call_names = []
        if tool_call_names is not _MISSING and tool_call_names:
            logger.debug(
                f"检测到工具调用中间响应，不计入记忆总结轮数: {tool_call_names}"
            )
            return

        completion_text = str(getattr(resp, "completion_text", "") or "").strip()
        if not completion_text:
            logger.debug("LLM 助手响应为空，不计入记忆总结轮数。")
            return

        context_history = plugin.context_manager.get_history(session_id)
        user_was_recorded = _get_event_extra(
            event, USER_RECORDED_EXTRA_KEY, False
        ) or _has_turn_marker(plugin, "_mnemosyne_recorded_user_turns", turn_marker)
        if not user_was_recorded:
            logger.debug(
                "当前轮未经过 Mnemosyne 用户消息记录，跳过响应记录但继续检查总结。"
            )
            await _check_and_trigger_summary(
                plugin,
                session_id,
                context_history,
                persona_id,
            )
            return

        assistant_already_recorded = _get_event_extra(
            event, ASSISTANT_RECORDED_EXTRA_KEY, False
        ) or _has_turn_marker(
            plugin,
            "_mnemosyne_recorded_assistant_turns",
            turn_marker,
        )
        if assistant_already_recorded:
            logger.debug(f"会话 {session_id} 当前轮助手回复已记录，跳过重复计数。")
            return

        _append_tool_context_if_enabled(plugin, event, session_id, turn_marker)

        logger.debug(f"返回的内容：{completion_text}")
        plugin.context_manager.add_message(
            session_id,
            "assistant",
            completion_text,
            metadata={"speaker_id": "assistant"},
        )
        plugin.msg_counter.increment_counter(session_id)
        _set_event_extra(event, ASSISTANT_RECORDED_EXTRA_KEY, True)
        _mark_turn_once(plugin, "_mnemosyne_recorded_assistant_turns", turn_marker)

        # 判断是否需要总结。放在助手回复记录之后，确保总结素材包含本轮最终回复。
        await _check_and_trigger_summary(
            plugin,
            session_id,
            plugin.context_manager.get_history(session_id),
            persona_id,
        )

    except Exception as e:
        logger.error(f"处理 LLM 响应后的记忆记录失败: {e}", exc_info=True)


# 记忆查询 (RAG) 相关函数
async def _check_rag_prerequisites(plugin: "Mnemosyne") -> bool:
    """
    检查 RAG 查询的前提条件是否满足。

    Args:
        plugin: Mnemosyne 插件实例。

    Returns:
        True 如果前提条件满足，False 否则。
    """
    # logger = plugin.logger
    vector_db = _get_vector_db(plugin)
    if not vector_db:
        logger.warning("向量数据库未初始化，无法查询长期记忆。")
        return False
    if not vector_db.is_connected():
        logger.warning("向量数据库未连接，无法查询长期记忆。")
        return False
    # 检查 Embedding Provider 是否就绪，支持延迟加载
    if not plugin.embedding_provider and not plugin._embedding_provider_ready:
        logger.warning("Embedding Provider 未初始化，部分功能可能受限。")
        return False
    if not plugin.msg_counter:
        logger.error("消息计数器未初始化，将无法实现记忆总结")
        return False
    return True


async def _get_persona_id(plugin: "Mnemosyne", event: AstrMessageEvent) -> str | None:
    """
    获取当前会话的人格 ID。

    Args:
        plugin: Mnemosyne 插件实例。
        event: 消息事件。

    Returns:
        人格 ID 字符串，如果没有人格或发生错误则为 None。
    """
    # logger = plugin.logger
    # 获取 conversation_id 用于获取人格配置
    conversation_id = (
        await plugin.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
    )
    conversation = await plugin.context.conversation_manager.get_conversation(
        event.unified_msg_origin, str(conversation_id)
    )
    persona_id = conversation.persona_id if conversation else None

    if not persona_id or persona_id == "[%None]":
        if plugin.config.get("personality_fallback", False):
            # 尝试获取默认人格
            try:
                fallback_id = (
                    (plugin.context.get_config(event.unified_msg_origin) or {})
                    .get("provider_settings", {})
                    .get("default_personality", DEFAULT_PERSONA_ON_NONE)
                )
                if not fallback_id or fallback_id == "[%None]":
                    fallback_id = DEFAULT_PERSONA_ON_NONE
                message = f"当前会话 (ID: {event.unified_msg_origin}) 未配置人格，将使用默认人格 '{fallback_id}' 进行记忆操作（如果启用人格过滤）。"
            except Exception as e:
                logger.error(f"获取默认人格失败: {e}，回退到占位符")
                fallback_id = DEFAULT_PERSONA_ON_NONE
                message = f"当前会话 (ID: {event.unified_msg_origin}) 未配置人格，将使用占位符 '{fallback_id}' 进行记忆操作（如果启用人格过滤）。"
        else:
            # 不使用默认人格，避免记忆错乱
            fallback_id = DEFAULT_PERSONA_ON_NONE
            message = f"当前会话 (ID: {event.unified_msg_origin}) 未配置人格，将使用占位符 '{fallback_id}' 进行记忆操作（如果启用人格过滤）。"

        logger.warning(message)

        if plugin.config.get("use_personality_filtering", False):
            persona_id = fallback_id
        else:
            persona_id = None
    return persona_id


def _attach_summary_task_callback(
    task: asyncio.Task,
    plugin: "Mnemosyne",
    session_id: str,
    tool_context_markers: set[str],
    pre_summary_count: int | None = None,
) -> None:
    """
    后台总结结束后清理本次任务捕获的临时 tool 上下文。

    Args:
        task: 总结任务。
        plugin: Mnemosyne 插件实例。
        session_id: 会话 ID。
        tool_context_markers: 本次总结任务捕获的临时 tool 上下文标记。
        pre_summary_count: 提交任务前的消息计数快照；任务失败时用于回滚
            计数器，使下一轮对话重新触发总结（issue #150）。
    """

    def task_done_callback(t: asyncio.Task):
        succeeded = False
        try:
            # 获取任务结果，如果有异常会在这里抛出
            succeeded = bool(t.result())
        except asyncio.CancelledError:
            logger.info(f"总结任务被取消 (session: {session_id})")
        except Exception as e:
            logger.error(
                f"后台总结任务执行失败 (session: {session_id}): {e}", exc_info=True
            )
        finally:
            _clear_recorded_tool_context(plugin, session_id, tool_context_markers)

        if succeeded:
            return

        # 总结失败时回滚计数器，让下一轮对话重新触发总结，
        # 避免本轮记忆因 LLM 请求失败而被静默丢弃（issue #150）。
        # 未传入计数值快照的调用方（如部分测试）跳过回滚。
        if pre_summary_count is None:
            return

        try:
            if plugin.msg_counter:
                plugin.msg_counter.restore_counter(session_id, pre_summary_count)
                logger.warning(
                    f"总结任务未成功 (session: {session_id})，"
                    f"已恢复计数器至 {pre_summary_count}，将在下一轮对话重新触发总结。"
                )
        except Exception as e:
            logger.error(f"回滚会话 {session_id} 的消息计数器失败: {e}", exc_info=True)

    task.add_done_callback(task_done_callback)


async def _check_and_trigger_summary(
    plugin: "Mnemosyne",
    session_id: str,
    context: list[dict],
    persona_id: str | None,
):
    """
    检查是否满足总结条件并触发总结任务。

    Args:
        plugin: Mnemosyne 插件实例。
        session_id: 会话 ID。
        context: 请求上下文列表。
        persona_id: 人格 ID.
    """
    # M24 修复: 添加 msg_counter 的类型检查
    # num_pairs 是对话轮数，msg_counter 计数的是消息条数（一问一答=2条消息）
    # 所以需要用 num_pairs * 2 来比较
    num_pairs = plugin.config.get("num_pairs", 5)
    if (
        plugin.msg_counter
        and plugin.msg_counter.adjust_counter_if_necessary(session_id, context)
        and plugin.msg_counter.get_counter(session_id) >= num_pairs * 2
    ):
        logger.info(f"对话已达到 {num_pairs} 轮，开始总结历史对话...")
        # M24 修复: 添加类型忽略，context 来自运行时的上下文
        history_contents = format_context_to_string(
            context,  # type: ignore
            num_pairs * 2,  # 传递消息条数而不是轮数
            include_tool_context=_summary_should_include_tool_context(plugin),
        )
        tool_context_markers = _collect_tool_context_markers(context)

        task = asyncio.create_task(
            handle_summary_long_memory(
                plugin,
                persona_id,
                session_id,
                history_contents,
                context_history=context,
            )
        )
        # 记录提交总结任务前的计数值，供失败回滚使用（issue #150）
        pre_summary_count = plugin.msg_counter.get_counter(session_id)
        _attach_summary_task_callback(
            task, plugin, session_id, tool_context_markers, pre_summary_count
        )
        logger.info("总结历史对话任务已提交到后台执行。")
        # M24 修复: 添加类型检查
        if plugin.msg_counter:
            plugin.msg_counter.reset_counter(session_id)


async def _perform_vector_db_search(
    plugin: "Mnemosyne",
    query_vector: list[float],
    session_id: str | None,
    persona_id: str | None,
    query_text: str = "",
    sender_id: str | None = None,
) -> list[dict] | None:
    """
    执行向量数据库搜索。

    Args:
        plugin: Mnemosyne 插件实例。
        query_vector: 查询向量。
        session_id: 会话 ID。
        persona_id: 人格 ID。

    Returns:
        搜索结果列表，如果没有找到或出错则为 None。
    """
    # logger = plugin.logger
    filters = []

    # 检查是否启用了会话过滤
    use_session_filtering = plugin.config.get("use_session_filtering", True)

    if use_session_filtering:
        if session_id:
            # 安全检查：验证 session_id 格式
            if not validate_session_id(session_id):
                logger.error(f"session_id 格式验证失败: {session_id}")
                return None

            # 使用安全的表达式构建方法
            try:
                session_filter = safe_build_milvus_expression(
                    "session_id", session_id, "=="
                )
                filters.append(session_filter)
                logger.debug(f"已启用会话过滤，将使用会话 '{session_id}' 过滤记忆。")
            except ValueError as e:
                logger.error(f"构建 session_id 过滤表达式失败: {e}")
                return None
        else:
            logger.warning("无法获取当前 session_id，将不按 session 过滤记忆！")
    else:
        logger.info("会话过滤已禁用，将在所有会话中搜索记忆。")

    use_personality_filtering = plugin.config.get("use_personality_filtering", False)
    effective_persona_id_for_filter = persona_id
    if use_personality_filtering and effective_persona_id_for_filter:
        # 安全检查：验证 personality_id 格式
        if not validate_personality_id(effective_persona_id_for_filter):
            logger.warning(
                f"personality_id 格式验证失败: {effective_persona_id_for_filter}，跳过人格过滤"
            )
        else:
            # 使用安全的表达式构建方法
            try:
                persona_filter = safe_build_milvus_expression(
                    "personality_id", effective_persona_id_for_filter, "=="
                )
                filters.append(persona_filter)
                logger.debug(
                    f"将使用人格 '{effective_persona_id_for_filter}' 过滤记忆。"
                )
            except ValueError as e:
                logger.error(f"构建 personality_id 过滤表达式失败: {e}")
    elif use_personality_filtering:
        logger.debug("启用了人格过滤，但当前无有效人格 ID，不按人格过滤。")

    search_expression = " and ".join(filters) if filters else ""
    collection_name = plugin.collection_name
    top_k = plugin.config.get("top_k", DEFAULT_TOP_K)
    timeout_seconds = plugin.config.get("milvus_search_timeout", DEFAULT_MILVUS_TIMEOUT)

    candidate_limit = min(top_k * 4, 60)
    logger.info(
        f"开始在集合 '{collection_name}' 中搜索相关记忆 (TopK: {top_k}, Candidates: {candidate_limit}, Filter: '{search_expression or '无'}')"
    )

    vector_db = _get_vector_db(plugin)
    if not vector_db:
        logger.error("向量数据库不可用")
        return None

    try:
        detailed_results = await asyncio.wait_for(
            asyncio.to_thread(
                vector_db.search,
                collection_name=collection_name,
                query_vector=query_vector,
                top_k=candidate_limit,
                filters=search_expression,
                search_params=plugin.search_params,
                output_fields=plugin.output_fields_for_query,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.error(f"向量数据库搜索超时 ({timeout_seconds} 秒)，操作已取消。")
        return None
    except MilvusException as me:
        logger.error(f"Milvus 搜索操作失败: {me}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"执行向量数据库搜索时发生未知错误: {e}", exc_info=True)
        return None

    if not detailed_results:
        logger.info("向量搜索未找到相关记忆。")
        return None

    post_processed = _post_process_search_results(
        plugin=plugin,
        detailed_results=detailed_results,
        query_text=query_text,
        sender_id=sender_id,
    )
    return post_processed[:top_k]


async def _perform_milvus_search(
    plugin: "Mnemosyne",
    query_vector: list[float],
    session_id: str | None,
    persona_id: str | None,
    query_text: str = "",
    sender_id: str | None = None,
) -> list[dict] | None:
    """旧函数名兼容：实际搜索当前配置的向量数据库。"""
    return await _perform_vector_db_search(
        plugin=plugin,
        query_vector=query_vector,
        session_id=session_id,
        persona_id=persona_id,
        query_text=query_text,
        sender_id=sender_id,
    )


def _process_milvus_hits(hits) -> list[dict[str, Any]]:
    """
    处理 Milvus SearchResults 中的 Hits 对象，使用基于索引的遍历方式
    提取有效的记忆实体数据。

    Args:
        hits: 从 Milvus 搜索结果 search_results[0] 中获取的 Hits 对象。

    Returns:
        一个包含提取到的记忆实体字典的列表。如果没有任何有效实体被提取，
        则返回空列表 []。
    """
    detailed_results: list[dict[str, Any]] = []  # 初始化结果列表，指定类型

    # 使用索引遍历 hits 对象，以绕过 SequenceIterator 的迭代问题
    if hits:  # 确保 hits 对象不是空的或 None
        try:
            num_hits = len(hits)  # 获取命中数量
            logger.debug(f"Milvus 返回了 {num_hits} 条原始命中结果。")

            # 使用索引进行遍历
            for i in range(num_hits):
                try:
                    hit = hits[i]  # 通过索引获取单个 Hit 对象

                    # 检查 hit 对象及其 entity 属性是否存在且有效
                    # 使用 hasattr 更健壮，避免在 entity 属性不存在时报错
                    if hit and hasattr(hit, "entity") and hit.entity:
                        # 提取 entity 数据，使用 .get() 避免 KeyError
                        # 假设 entity.to_dict() 返回的字典中有 "entity" 键
                        entity_data = hit.entity.to_dict().get("entity")
                        # 如果成功提取到数据，则添加到结果列表
                        if entity_data:
                            # 附带 Milvus 距离信息用于后续关键词/图谱重排
                            if isinstance(entity_data, dict):
                                entity_data = dict(entity_data)
                                distance = getattr(hit, "distance", None)
                                if isinstance(distance, (int, float)):
                                    entity_data["_distance"] = float(distance)
                            detailed_results.append(entity_data)
                        else:
                            # 如果 entity 存在但提取的数据为空，可能是数据结构问题
                            logger.warning(
                                f"命中结果索引 {i} 处的 entity 数据为空或无效，已跳过。"
                            )
                    else:
                        # 如果 hit 或 entity 无效，则跳过
                        logger.debug(f"命中结果索引 {i} 处对象或 entity 无效，已跳过。")

                except Exception as e:
                    # 处理访问或处理单个 hit 时可能出现的错误
                    logger.error(
                        f"处理索引 {i} 处的命中结果时发生错误: {e}", exc_info=True
                    )
                    # 发生错误时继续处理下一个 hit，不中断整个流程

        except Exception as e:
            # 处理获取长度或设置循环时可能出现的更严重的错误
            # 如果在这里发生错误，detailed_results 可能不完整或为空
            logger.error(f"执行基于索引的命中结果处理时发生错误: {e}", exc_info=True)

    # 记录成功处理并提取记忆的记录数
    logger.debug(f"成功处理并提取记忆的记录数: {len(detailed_results)} 条。")

    return detailed_results


# LLM 响应处理相关函数
def _format_and_inject_memory(
    plugin: "Mnemosyne", detailed_results: list[dict], req: ProviderRequest
):
    """
    格式化搜索结果并注入到 ProviderRequest 中。

    Args:
        plugin: Mnemosyne 插件实例。
        detailed_results: 详细的搜索结果列表。
        req: ProviderRequest 对象。
    """
    # logger = plugin.logger
    if not detailed_results:
        logger.info("未找到或获取到相关的长期记忆，不进行补充。")
        return

    long_memory_prefix = plugin.config.get(
        "long_memory_prefix", "<Mnemosyne> 长期记忆片段："
    )
    long_memory_suffix = plugin.config.get("long_memory_suffix", "</Mnemosyne>")
    long_memory = f"{long_memory_prefix}\n"

    for result in detailed_results:
        content = strip_memory_meta(str(result.get("content", "内容缺失")))
        ts = result.get("create_time")
        try:
            time_str = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                if ts
                else "未知时间"
            )
        except (TypeError, ValueError):
            time_str = f"时间戳: {ts}" if ts else "未知时间"

        memory_entry_format = plugin.config.get(
            "memory_entry_format", "- [{time}] {content}"
        )
        long_memory += memory_entry_format.format(time=time_str, content=content) + "\n"

    long_memory += long_memory_suffix

    logger.info(f"补充了 {len(detailed_results)} 条长期记忆到提示中。")
    logger.debug(f"补充内容:\n{long_memory}")

    injection_method = plugin.config.get("memory_injection_method", "user_prompt")
    injection_position = plugin.config.get("memory_injection_position", "prepend")
    if injection_position not in {"prepend", "append"}:
        injection_position = "prepend"

    # 清理插入的长期记忆内容
    clean_contexts(plugin, req)
    if injection_method == "user_prompt":
        current_prompt = req.prompt if isinstance(req.prompt, str) else ""
        if injection_position == "append":
            req.prompt = current_prompt + "\n" + long_memory
        else:
            req.prompt = long_memory + "\n" + current_prompt

    elif injection_method == "system_prompt":
        current_system_prompt = (
            req.system_prompt if isinstance(req.system_prompt, str) else ""
        )
        if injection_position == "append":
            req.system_prompt = current_system_prompt + long_memory
        else:
            req.system_prompt = long_memory + current_system_prompt

    elif injection_method == "insert_system_prompt":
        payload = {"role": "system", "content": long_memory}
        if injection_position == "append":
            req.contexts.append(payload)
        else:
            req.contexts.insert(0, payload)

    elif injection_method == "extra_user_parts":
        # 模仿 koko toolbox 的 <system_WARNING> 注入方式：
        # 将记忆作为一个额外的用户内容块追加到 req.extra_user_content_parts，
        # AstrBot 会把它拼接到“当前这条用户消息”之后再发给 LLM。
        _inject_via_extra_user_parts(req, long_memory, injection_position)

    else:
        logger.warning(
            f"未知的记忆注入方法 '{injection_method}'，将默认追加到用户 prompt。"
        )
        current_prompt = req.prompt if isinstance(req.prompt, str) else ""
        req.prompt = long_memory + "\n" + current_prompt


def _mark_content_part_as_temp(part: Any) -> None:
    marker = getattr(part, "mark_as_temp", None)
    if callable(marker):
        marker()
        return

    # 兼容测试桩或字典式 ContentPart；持久化会过滤 _no_save=True。
    if isinstance(part, dict):
        part["_no_save"] = True
        return

    try:
        setattr(part, "_no_save", True)
    except Exception:
        logger.debug("无法为 extra_user_content_parts 标记临时内容", exc_info=True)


def _inject_via_extra_user_parts(
    req: ProviderRequest, long_memory: str, injection_position: str
):
    """以 koko toolbox 的方式，将记忆作为额外用户内容块注入。

    使用 TextPart，避免克隆 ImageURLPart/AudioURLPart 时因 text 字段不兼容而失败。
    注入的记忆必须标记为临时内容，防止持久化进会话历史。
    """
    try:
        parts = getattr(req, "extra_user_content_parts", None)
        if parts is not None:
            from astrbot.core.agent.message import TextPart

            part = TextPart(text=long_memory)
            _mark_content_part_as_temp(part)
            req.extra_user_content_parts.append(part)
            logger.debug("已通过 extra_user_content_parts 注入长期记忆。")
            return
    except Exception as e:
        logger.warning(
            f"通过 extra_user_content_parts 注入记忆失败，回退到 prompt: {e}"
        )

    # 兜底：按配置写回 prompt。
    current_prompt = req.prompt if isinstance(req.prompt, str) else ""
    if injection_position == "append":
        req.prompt = current_prompt + "\n" + long_memory
    else:
        req.prompt = long_memory + "\n" + current_prompt


# 删除补充的长期记忆函数
def clean_contexts(plugin: "Mnemosyne", req: ProviderRequest):
    """
    删除长期记忆中的标签
    """
    injection_method = plugin.config.get("memory_injection_method", "user_prompt")
    contexts_memory_len = plugin.config.get("contexts_memory_len", 0)
    if injection_method == "user_prompt":
        req.contexts = remove_mnemosyne_tags(req.contexts, contexts_memory_len)
    elif injection_method == "system_prompt":
        req.system_prompt = remove_system_mnemosyne_tags(
            req.system_prompt, contexts_memory_len
        )
    elif injection_method == "insert_system_prompt":
        req.contexts = remove_system_content(req.contexts, contexts_memory_len)
    elif injection_method == "extra_user_parts":
        # extra_user_parts 注入的是临时 ContentPart，不应清理 req.contexts；
        # 历史里可能存在的 list 型多模态内容也不应由这里重写。
        pass
    return


# 记忆总结相关函数
async def _check_summary_prerequisites(plugin: "Mnemosyne", memory_text: str) -> bool:
    """
    检查记忆总结的前提条件是否满足。

    Args:
        plugin: Mnemosyne 插件实例。
        memory_text: 记忆文本。

    Returns:
        True 如果前提条件满足，False 否则。
    """
    # logger = plugin.logger
    vector_db = _get_vector_db(plugin)
    if not vector_db or not vector_db.is_connected():
        logger.error("向量数据库不可用，无法存储总结后的长期记忆。")
        return False
    if not plugin.embedding_provider:
        logger.error("Embedding Provider 不可用，无法向量化总结记忆。")
        return False
    if not memory_text or not memory_text.strip():
        logger.warning("尝试总结空的或仅包含空白的记忆文本，跳过。")
        return False
    return True


def _summary_response_has_text(response: Any) -> bool:
    if isinstance(response, LLMResponse):
        completion_text = response.completion_text
    elif isinstance(response, dict):
        completion_text = response.get("completion_text")
    else:
        return False
    return isinstance(completion_text, str) and bool(completion_text.strip())


def _build_summary_speaker_mapping_prompt(
    plugin: "Mnemosyne",
    persona_id: str | None,
    session_id: str,
    context_history: list[dict] | None,
) -> str:
    template = plugin.config.get(
        "summary_speaker_mapping_prompt",
        DEFAULT_SUMMARY_SPEAKER_MAPPING_PROMPT,
    )
    if not isinstance(template, str) or not template.strip():
        return ""

    sender_id = "UNKNOWN_USER"
    sender_name = "用户"
    for message in reversed(context_history or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        metadata = message.get("metadata")
        if isinstance(metadata, dict):
            candidate_id = metadata.get("speaker_id")
            if isinstance(candidate_id, str) and candidate_id.strip():
                sender_id = candidate_id.strip()
        content = message.get("content")
        if isinstance(content, str):
            matched = re.match(r"^\[([^\]()]+)\(([^()]*)\)\]:", content)
            if matched and matched.group(1).strip():
                sender_name = matched.group(1).strip()
        break

    replacements = {
        "{persona_id}": persona_id or DEFAULT_PERSONA_ON_NONE,
        "{session_id}": session_id,
        "{sender_id}": sender_id,
        "{sender_name}": sender_name,
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered.strip()


def _get_current_summary_provider(plugin: "Mnemosyne", session_id: str):
    if plugin.provider:
        return plugin.provider
    try:
        return plugin.context.get_using_provider(umo=session_id)
    except TypeError:
        return plugin.context.get_using_provider()


async def _get_summary_llm_response(
    plugin: "Mnemosyne",
    memory_text: str,
    *,
    persona_id: str | None = None,
    session_id: str = "",
    context_history: list[dict] | None = None,
) -> LLMResponse | None:
    """
    请求 LLM 进行记忆总结。

    Args:
        plugin: Mnemosyne 插件实例。
        memory_text: 需要总结的记忆文本。

    Returns:
        LLMResponse 对象，如果请求失败则为 None。
    """
    # logger = plugin.logger
    providers: list[tuple[str, Any]] = []
    try:
        primary_provider = _get_current_summary_provider(plugin, session_id)
        if primary_provider:
            providers.append(("主", primary_provider))
    except Exception as e:
        logger.error(f"获取 LLM Provider 时出错: {e}", exc_info=True)

    fallback_provider_id = plugin.config.get("summary_fallback_provider_id", "")
    if isinstance(fallback_provider_id, str) and fallback_provider_id.strip():
        try:
            fallback_provider = plugin.context.get_provider_by_id(
                fallback_provider_id.strip()
            )
            if fallback_provider and all(
                fallback_provider is not provider for _, provider in providers
            ):
                providers.append(("备用", fallback_provider))
            elif not fallback_provider:
                logger.warning(
                    f"未找到备用总结 Provider: {fallback_provider_id.strip()}"
                )
        except Exception as e:
            logger.error(f"获取备用总结 Provider 时出错: {e}", exc_info=True)

    if not providers:
        logger.error("无法获取用于总结记忆的 LLM Provider。")
        return None

    long_memory_prompt = plugin.config.get(
        "long_memory_prompt",
        "请将以下多轮对话历史总结为一段简洁、客观、包含关键信息的长期记忆条目:",
    )
    summary_llm_config = plugin.config.get("summary_llm_config", {})

    logger.debug(
        f"请求 LLM 总结短期记忆，提示: '{long_memory_prompt[:50]}...', 内容长度: {len(memory_text)}"
    )

    try:
        summary_contexts = [{"role": "system", "content": long_memory_prompt}]
        if plugin.config.get("use_summary_time_anchor", True):
            now_str = datetime.now().astimezone().isoformat(timespec="seconds")
            summary_contexts.append(
                {
                    "role": "system",
                    "content": (
                        f"当前绝对时间：{now_str}。"
                        "如果原始对话未明确给出具体日期/年份，禁止臆造精确日期；"
                        "请使用“近期/之前/后来”等相对表达。"
                    ),
                }
            )

        speaker_mapping = _build_summary_speaker_mapping_prompt(
            plugin,
            persona_id,
            session_id,
            context_history,
        )
        if speaker_mapping:
            summary_contexts.append({"role": "system", "content": speaker_mapping})

        for provider_kind, llm_provider in providers:
            try:
                llm_response = await llm_provider.text_chat(  # type: ignore
                    prompt=memory_text,
                    contexts=summary_contexts,
                    **summary_llm_config,
                )
                logger.debug(f"{provider_kind} LLM 总结响应原始数据: {llm_response}")
                if _summary_response_has_text(llm_response):
                    return llm_response
                logger.warning(f"{provider_kind}总结 Provider 返回空内容。")
            except Exception as e:
                logger.error(
                    f"{provider_kind}总结 Provider 请求失败: {e}",
                    exc_info=True,
                )
        return None
    except Exception as e:
        logger.error(f"构造总结请求时失败: {e}", exc_info=True)
        return None


def _extract_summary_text(plugin: "Mnemosyne", llm_response: LLMResponse) -> str | None:
    """
    从 LLM 响应中提取总结文本并进行校验。

    Args:
        plugin: Mnemosyne 插件实例。
        llm_response: LLMResponse 对象。

    Returns:
        总结文本字符串，如果提取失败则为 None。
    """
    # logger = plugin.logger
    completion_text = None
    if isinstance(llm_response, LLMResponse):
        completion_text = llm_response.completion_text
        # role = llm_response.role
    elif isinstance(llm_response, dict):
        completion_text = llm_response.get("completion_text")
        # role = llm_response.get("role")
    else:
        logger.error(f"LLM 总结返回了未知类型的数据: {type(llm_response)}")
        return None

    if not completion_text or not completion_text.strip():
        logger.error(f"LLM 总结响应无效或内容为空。原始响应: {llm_response}")
        return None

    summary_text = completion_text.strip()
    logger.info(f"LLM 成功生成记忆总结，长度: {len(summary_text)}")
    return summary_text


async def _store_summary_to_vector_db(
    plugin: "Mnemosyne",
    persona_id: str | None,
    session_id: str,
    summary_text: str,
    embedding_vector: list[float],
) -> bool:
    """
    将总结文本和向量存储到向量数据库中。

    Args:
        plugin: Mnemosyne 插件实例。
        persona_id: 人格 ID。
        session_id: 会话 ID。
        summary_text: 总结文本。
        embedding_vector: 总结文本的 Embedding 向量。
    """
    # logger = plugin.logger
    collection_name = plugin.collection_name
    current_timestamp = int(time.time())

    effective_persona_id = (
        persona_id
        if persona_id
        else plugin.config.get("default_persona_id_on_none", DEFAULT_PERSONA_ON_NONE)
    )

    data_to_insert = [
        {
            "personality_id": effective_persona_id,
            "session_id": session_id,
            "content": summary_text,
            VECTOR_FIELD_NAME: embedding_vector,
            "create_time": current_timestamp,
        }
    ]

    logger.info(
        f"准备向集合 '{collection_name}' 插入 1 条总结记忆 (Persona: {effective_persona_id}, Session: {session_id[:8]}...)"
    )
    mutation_result = None

    vector_db = _get_vector_db(plugin)
    if not vector_db:
        logger.error("向量数据库不可用")
        return False

    try:

        def _insert_data():
            return vector_db.insert(
                collection_name=collection_name,
                data=data_to_insert,
            )

        mutation_result = await asyncio.to_thread(_insert_data)
    except (MilvusException, ConnectionError, ValueError) as e:
        logger.error(f"向向量数据库插入总结记忆时出错: {e}", exc_info=True)
    finally:
        # 确保资源清理和错误日志记录
        if mutation_result is None:
            logger.error(
                f"Milvus 插入操作失败，未返回结果。集合: {collection_name}, 数据: {summary_text[:100]}..."
            )
        else:
            logger.debug("Milvus 插入操作完成，正在进行资源清理。")

    if mutation_result and mutation_result.insert_count > 0:
        inserted_ids = mutation_result.primary_keys
        logger.info(f"成功插入总结记忆到向量数据库。插入 ID: {inserted_ids}")

        try:
            logger.debug(
                f"正在刷新 (Flush) 集合 '{collection_name}' 以确保记忆立即可用..."
            )

            def _flush_collection():
                return vector_db.flush([collection_name])

            await asyncio.to_thread(_flush_collection)
            logger.debug(f"集合 '{collection_name}' 刷新完成。")
            return True

        except Exception as flush_err:
            logger.error(
                f"刷新集合 '{collection_name}' 时出错: {flush_err}",
                exc_info=True,
            )
            return False
    else:
        logger.error(
            f"插入总结记忆到向量数据库失败。MutationResult: {mutation_result}. LLM 回复: {summary_text[:100]}..."
        )
    return False


async def _store_summary_to_milvus(
    plugin: "Mnemosyne",
    persona_id: str | None,
    session_id: str,
    summary_text: str,
    embedding_vector: list[float],
) -> bool:
    """旧函数名兼容：实际写入当前配置的向量数据库。"""
    return await _store_summary_to_vector_db(
        plugin=plugin,
        persona_id=persona_id,
        session_id=session_id,
        summary_text=summary_text,
        embedding_vector=embedding_vector,
    )


async def handle_summary_long_memory(
    plugin: "Mnemosyne",
    persona_id: str | None,
    session_id: str,
    memory_text: str,
    context_history: list[dict] | None = None,
) -> bool:
    """
    使用 LLM 总结短期对话历史形成长期记忆，并将其向量化后存入 Milvus。
    这是一个后台任务。
    """
    # logger = plugin.logger

    # --- 前置检查 ---
    if not await _check_summary_prerequisites(plugin, memory_text):
        return False

    try:
        # 1. 请求 LLM 进行总结
        llm_response = await _get_summary_llm_response(
            plugin,
            memory_text,
            persona_id=persona_id,
            session_id=session_id,
            context_history=context_history,
        )
        if not llm_response:
            return False

        # 2. 提取总结文本
        summary_text = _extract_summary_text(plugin, llm_response)
        if not summary_text:
            return False

        # 3. 获取总结文本的 Embedding
        # 使用 AstrBot EmbeddingProvider（异步）
        try:
            if not plugin.embedding_provider:
                logger.error("Embedding Provider 不可用，无法获取总结的 Embedding")
                return False

            # 使用 AstrBot EmbeddingProvider 的 get_embedding 方法
            embedding_vector = await plugin.embedding_provider.get_embedding(
                summary_text
            )

            if not embedding_vector:
                logger.error(f"无法获取总结文本的 Embedding: '{summary_text[:100]}...'")
                return False

        except (ConnectionError, ValueError, RuntimeError) as e:
            logger.error(
                f"获取总结文本 Embedding 时出错: '{summary_text[:100]}...' - {e}",
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.error(
                f"获取总结文本 Embedding 时发生未知错误: '{summary_text[:100]}...' - {e}",
                exc_info=True,
            )
            return False

        metadata: dict[str, Any] = {}
        if plugin.config.get("use_participant_filtering", False) or plugin.config.get(
            "use_lightweight_memory_graph", True
        ):
            metadata = _build_lightweight_graph_metadata(summary_text, context_history)
        stored_content = pack_memory_content(summary_text, metadata)

        # 4. 存储到向量数据库
        return await _store_summary_to_vector_db(
            plugin, persona_id, session_id, stored_content, embedding_vector
        )
    except Exception as e:
        logger.error(f"在总结或存储长期记忆的过程中发生严重错误: {e}", exc_info=True)
        return False


async def store_manual_memory(
    plugin: "Mnemosyne",
    event: AstrMessageEvent,
    memory_content: str,
    source: str = "manual",
    session_id: str | None = None,
    persona_id: str | None = None,
) -> bool:
    """
    直接写入一条长期记忆（不经过 LLM 总结），用于显式“记住”场景和手动命令。
    """
    normalized_content = (
        memory_content.strip() if isinstance(memory_content, str) else ""
    )
    if not normalized_content:
        logger.warning("手动记忆内容为空，已跳过。")
        return False

    if not await _check_summary_prerequisites(plugin, normalized_content):
        return False

    target_session_id = session_id or event.unified_msg_origin
    if not target_session_id or not validate_session_id(target_session_id):
        logger.error(f"手动记忆写入失败：无效 session_id={target_session_id}")
        return False

    target_persona = persona_id
    if not target_persona:
        target_persona = await _get_persona_id(plugin, event)

    if not plugin.embedding_provider:
        logger.error("手动记忆写入失败：Embedding Provider 不可用。")
        return False

    try:
        embedding_vector = await plugin.embedding_provider.get_embedding(
            normalized_content
        )
    except Exception as e:
        logger.error(f"手动记忆写入失败：获取 Embedding 异常: {e}", exc_info=True)
        return False

    if not embedding_vector:
        logger.error("手动记忆写入失败：Embedding 结果为空。")
        return False

    metadata = _build_lightweight_graph_metadata(
        normalized_content,
        context_history=[
            {
                "role": "user",
                "content": normalized_content,
                "metadata": _build_speaker_metadata(
                    _resolve_sender_identity(event, target_session_id)[1]
                ),
            }
        ],
    )
    metadata["source"] = source
    stored_content = pack_memory_content(normalized_content, metadata)

    return await _store_summary_to_vector_db(
        plugin=plugin,
        persona_id=target_persona,
        session_id=target_session_id,
        summary_text=stored_content,
        embedding_vector=embedding_vector,
    )


# 计时器
async def _periodic_summarization_check(plugin: "Mnemosyne"):
    """
    [后台任务] 定期检查并触发超时的会话总结

    S0 优化: 添加异常恢复机制，防止任务崩溃
    """
    logger.info(
        f"启动定期总结检查任务，检查间隔: {plugin.summary_check_interval}秒, 总结时间阈值: {plugin.summary_time_threshold}秒。"
    )

    # S0 优化: 异常恢复计数器
    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            await asyncio.sleep(plugin.summary_check_interval)  # <--- 等待指定间隔

            if not plugin.context_manager:
                # 如果上下文管理器未初始化，则跳过本次检查
                continue

            current_time = time.time()
            session_ids_to_check = list(plugin.context_manager.conversations.keys())

            # logger.debug(f"开始检查 {len(session_ids_to_check)} 个会话的总结超时...")

            for session_id in session_ids_to_check:
                try:
                    session_context = plugin.context_manager.get_session_context(
                        session_id
                    )
                    if not session_context:  # 会话可能在检查期间被移除
                        continue
                    # M24 修复: 添加 msg_counter 的类型检查
                    if (
                        not plugin.msg_counter
                        or plugin.msg_counter.get_counter(session_id) <= 0
                    ):
                        logger.debug(f"会话 {session_id} 没有新消息，跳过检查。")
                        continue

                    last_summary_time = session_context["last_summary_time"]

                    if current_time - last_summary_time > plugin.summary_time_threshold:
                        # logger.debug(f"current_time {current_time} - last_summary_time {last_summary_time} : {current_time - last_summary_time}")
                        logger.info(
                            f"会话 {session_id} 距离上次总结已超过阈值 ({plugin.summary_time_threshold}秒)，触发强制总结。"
                        )
                        # 运行总结
                        logger.info("开始总结历史对话...")
                        # M24 修复: 添加 msg_counter 的类型检查和类型忽略
                        counter = (
                            plugin.msg_counter.get_counter(session_id)
                            if plugin.msg_counter
                            else 0
                        )
                        history_contents = format_context_to_string(
                            session_context["history"],
                            counter,  # type: ignore
                            include_tool_context=_summary_should_include_tool_context(
                                plugin
                            ),
                        )
                        tool_context_markers = _collect_tool_context_markers(
                            session_context["history"]
                        )
                        persona_id = await _get_persona_id(
                            plugin, session_context["event"]
                        )
                        task = asyncio.create_task(
                            handle_summary_long_memory(
                                plugin,
                                persona_id,
                                session_id,
                                history_contents,
                                context_history=session_context["history"],
                            )
                        )
                        _attach_summary_task_callback(
                            task, plugin, session_id, tool_context_markers
                        )
                        logger.info("总结历史对话任务已提交到后台执行。")

                        # M24 修复: 添加 msg_counter 的类型检查
                        if plugin.msg_counter:
                            plugin.msg_counter.reset_counter(session_id)
                        plugin.context_manager.update_summary_time(session_id)

                except KeyError:
                    # 会话在获取 keys 后、处理前被删除，是正常情况
                    logger.debug(f"检查会话 {session_id} 时，会话已被移除。")
                except Exception as e:
                    logger.error(
                        f"检查或总结会话 {session_id} 时发生错误: {e}", exc_info=True
                    )

            # S0 优化: 成功完成一次循环，重置错误计数器
            consecutive_errors = 0

        except asyncio.CancelledError:
            logger.info("定期总结检查任务被取消。")
            break  # 退出循环
        except Exception as e:
            # S0 优化: 增强的异常处理和恢复机制
            consecutive_errors += 1
            logger.error(
                f"定期总结检查任务主循环发生错误 (连续错误次数: {consecutive_errors}/{max_consecutive_errors}): {e}",
                exc_info=True,
            )

            # 指数退避策略：等待时间随错误次数增加
            backoff_time = min(
                plugin.summary_check_interval * (2 ** (consecutive_errors - 1)), 300
            )
            logger.warning(f"将在 {backoff_time} 秒后重试后台总结任务...")

            try:
                await asyncio.sleep(backoff_time)
            except asyncio.CancelledError:
                logger.info("等待重试期间任务被取消。")
                break

            # 如果连续错误次数过多，记录严重警告但继续尝试
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    f"后台总结任务已连续失败 {consecutive_errors} 次，系统将继续尝试但可能存在严重问题，请检查日志并考虑重启插件。"
                )
                # 重置计数器以避免无限增长
                consecutive_errors = max_consecutive_errors - 1
