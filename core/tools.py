"""Mnemosyne 插件工具函数"""

import functools
import json
import re
from typing import Any
from urllib.parse import urlparse

from astrbot.api.event import AstrMessageEvent
from astrbot.core.log import LogManager

logger = LogManager.GetLogger(__name__)

MNEMO_META_PREFIX = "<MNEMO_META>"
MNEMO_META_SUFFIX = "</MNEMO_META>"
DEFAULT_EMBEDDING_MAX_CHARS = 4000
TRUNCATED_SUFFIX = "…(truncated)"
DEFAULT_SUMMARY_TEXT_MAX_CHARS = 2000
DEFAULT_TOOL_TEXT_MAX_CHARS = 1200
DEFAULT_TOOL_CONTEXT_LINE_LIMIT = 12


def _truncate_text(text: str, max_chars: int = DEFAULT_SUMMARY_TEXT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + TRUNCATED_SUFFIX


def _model_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {}


def _content_to_safe_text(
    content: Any, max_chars: int = DEFAULT_SUMMARY_TEXT_MAX_CHARS
) -> str:
    """将 AstrBot/OpenAI 风格上下文内容安全转为文本。"""

    if isinstance(content, str):
        if content.startswith("base64://") or content.startswith("data:image"):
            return "[图片]"
        if content.startswith("data:audio"):
            return "[音频]"
        return _truncate_text(content, max_chars)

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            item_dict = _model_to_dict(item)
            if not item_dict:
                continue

            item_type = item_dict.get("type")

            if item_type == "text":
                text = item_dict.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(_truncate_text(text, max_chars))
                continue

            if item_type == "image_url" or "image_url" in item_dict:
                parts.append("[图片]")
                continue

            if item_type == "audio_url" or "audio_url" in item_dict:
                parts.append("[音频]")
                continue

            if item_type == "think":
                continue

            if isinstance(item_type, str) and item_type:
                parts.append(f"[{item_type}]")

        return " ".join(p for p in parts if p)

    if isinstance(content, dict):
        if "image_url" in content or "audio_url" in content:
            return "[图片]" if "image_url" in content else "[音频]"
        text = content.get("text")
        if isinstance(text, str):
            return _truncate_text(text, max_chars)
        return ""

    return ""


def _safe_json_text(value: Any, max_chars: int = DEFAULT_TOOL_TEXT_MAX_CHARS) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return _truncate_text(text, max_chars)


def _normalize_tool_call(tool_call: Any) -> tuple[str, str, str]:
    tool_dict = _model_to_dict(tool_call)
    if not tool_dict:
        return "", "", ""

    call_id = str(tool_dict.get("id") or "").strip()
    function = tool_dict.get("function")
    function_dict = _model_to_dict(function)
    name = ""
    args: Any = ""

    if function_dict:
        name = str(function_dict.get("name") or "").strip()
        args = function_dict.get("arguments", "")
    elif isinstance(function, dict):
        name = str(function.get("name") or "").strip()
        args = function.get("arguments", "")
    else:
        name = str(tool_dict.get("name") or "").strip()
        args = tool_dict.get("arguments", "")

    if isinstance(args, str):
        args_text = _truncate_text(args, DEFAULT_TOOL_TEXT_MAX_CHARS)
    else:
        args_text = _safe_json_text(args)

    return call_id, name or "unknown_tool", args_text


def _format_tool_call_line(tool_call: Any) -> str:
    call_id, name, args_text = _normalize_tool_call(tool_call)
    suffix = f" id={call_id}" if call_id else ""
    if args_text:
        return f"assistant called tool {name}{suffix} args={args_text}"
    return f"assistant called tool {name}{suffix}"


def _iter_tool_call_result_items(tool_calls_result: Any) -> list[Any]:
    if not tool_calls_result:
        return []
    if isinstance(tool_calls_result, list):
        return tool_calls_result
    return [tool_calls_result]


def format_tool_calls_result_to_string(tool_calls_result: Any) -> str:
    """
    将 ProviderRequest.tool_calls_result 压缩成可总结的安全文本。
    """
    lines: list[str] = []
    for tool_result in _iter_tool_call_result_items(tool_calls_result):
        info = getattr(tool_result, "tool_calls_info", None)
        if info is None and isinstance(tool_result, dict):
            info = tool_result.get("tool_calls_info")
        info_dict = _model_to_dict(info)

        if info_dict:
            content_text = _content_to_safe_text(info_dict.get("content"))
            for tool_call in info_dict.get("tool_calls") or []:
                lines.append(_format_tool_call_line(tool_call))
            if content_text:
                lines.append(f"assistant tool-call context: {content_text}")

        result_messages = getattr(tool_result, "tool_calls_result", None)
        if result_messages is None and isinstance(tool_result, dict):
            result_messages = tool_result.get("tool_calls_result")
        if result_messages and not isinstance(result_messages, list):
            result_messages = [result_messages]

        for result_message in result_messages or []:
            result_dict = _model_to_dict(result_message)
            if not result_dict:
                continue
            call_id = str(result_dict.get("tool_call_id") or "").strip()
            content_text = _content_to_safe_text(
                result_dict.get("content"), DEFAULT_TOOL_TEXT_MAX_CHARS
            )
            if not content_text:
                continue
            id_text = f" id={call_id}" if call_id else ""
            lines.append(f"tool result{id_text}: {content_text}")

    return "\n".join(lines)


def resolve_max_prompt_chars(
    config: Any, default: int = DEFAULT_EMBEDDING_MAX_CHARS
) -> int:
    """
    从配置中解析 max_prompt_chars_for_embedding，并提供安全回退。
    """
    raw_value: Any = default
    try:
        if isinstance(config, dict):
            raw_value = config.get("max_prompt_chars_for_embedding", default)
        elif config is not None:
            getter = getattr(config, "get", None)
            if callable(getter):
                raw_value = getter("max_prompt_chars_for_embedding", default)
            else:
                raw_value = getattr(config, "max_prompt_chars_for_embedding", default)
        max_chars = int(raw_value)
    except (TypeError, ValueError):
        return default

    return max_chars if max_chars > 0 else default


def truncate_for_embedding(
    text: str, max_chars: int, append_suffix: bool = False
) -> tuple[str, bool]:
    """
    按长度限制截断文本，返回 (处理后文本, 是否发生截断)。
    """
    normalized_text = text if isinstance(text, str) else str(text)
    if max_chars <= 0:
        max_chars = DEFAULT_EMBEDDING_MAX_CHARS
    if len(normalized_text) <= max_chars:
        return normalized_text, False

    truncated = normalized_text[:max_chars]
    if append_suffix:
        truncated += TRUNCATED_SUFFIX
    return truncated, True


def parse_address(address: str):
    """
    解析地址，提取出主机名和端口号。
    如果地址没有协议前缀，则默认添加 "http://"
    """
    if not (address.startswith("http://") or address.startswith("https://")):
        address = "http://" + address
    parsed = urlparse(address)
    host = parsed.hostname
    port = (
        parsed.port if parsed.port is not None else 19530
    )  # 如果未指定端口，默认使用19530
    return host, port


def content_to_str(func):
    """
    实现一个装饰器，将输入的内容全部转化为字符串
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        str_args = [str(arg) for arg in args]
        str_kwargs = {k: str(v) for k, v in kwargs.items()}
        logger.debug(
            f"Function '{func.__name__}' called with arguments: args={str_args}, kwargs={str_kwargs}"
        )
        return func(*str_args, **str_kwargs)

    return wrapper


def remove_mnemosyne_tags(
    contents: list[dict[str, Any]], contexts_memory_len: int = 0
) -> list[dict[str, Any]]:
    """
    使用正则表达式去除LLM上下文中的<mnemosyne> </mnemosyne>标签对。
    - contexts_memory_len > 0: 保留最新的N个标签对。
    - contexts_memory_len == 0: 移除所有标签对。
    - contexts_memory_len < 0: 保留所有标签对，不作任何删除。
    """
    if contexts_memory_len < 0:
        return contents

    compiled_regex = re.compile(r"<Mnemosyne>.*?</Mnemosyne>", re.DOTALL)
    cleaned_contents: list[dict[str, Any]] = []

    def copy_with_cleaned_content(
        content_item: dict[str, Any], cleaned_content: Any
    ) -> dict[str, Any]:
        cleaned_item = content_item.copy()
        cleaned_item["content"] = cleaned_content
        return cleaned_item

    if contexts_memory_len == 0:
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                # 关键修复：多模态内容（list/dict 等）不能强制转换为字符串。
                # 只有在 content 为 str 时才需要清理标签。
                if isinstance(original_text, str):
                    cleaned_text = compiled_regex.sub("", original_text)
                    cleaned_contents.append(
                        copy_with_cleaned_content(content_item, cleaned_text)
                    )
                else:
                    cleaned_contents.append(content_item)
            else:
                cleaned_contents.append(content_item)
    else:  # contexts_memory_len > 0
        all_mnemosyne_blocks: list[str] = []
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                if isinstance(original_text, str):
                    found_blocks = compiled_regex.findall(original_text)
                    all_mnemosyne_blocks.extend(found_blocks)

        blocks_to_keep: set[str] = set(all_mnemosyne_blocks[-contexts_memory_len:])

        def replace_logic(match: re.Match) -> str:
            block = match.group(0)
            return block if block in blocks_to_keep else ""

        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")

                # M14 修复: 改进逻辑流程，确保正确处理各种情况
                # 使用 elif 形成互斥逻辑，避免重复处理
                if isinstance(original_text, list):
                    # 1. 如果内容是列表（多模态消息），直接保留原样
                    cleaned_contents.append(content_item)
                elif isinstance(original_text, str):
                    # 2. 如果内容是字符串，检查是否需要清理标签
                    if compiled_regex.search(original_text):
                        # 内容包含标签，进行清理
                        cleaned_text = compiled_regex.sub(replace_logic, original_text)
                        cleaned_contents.append(
                            copy_with_cleaned_content(content_item, cleaned_text)
                        )
                    else:
                        # 内容不包含标签，直接保留
                        cleaned_contents.append(content_item)
                else:
                    # 3. 其他类型（不应该出现），记录警告并保留原始内容
                    logger.warning(
                        f"遇到意外的 content 类型: {type(original_text).__name__}，将保留原始内容"
                    )
                    cleaned_contents.append(content_item)
            else:
                # 非 user 角色的消息，直接保留
                cleaned_contents.append(content_item)

    return cleaned_contents


def remove_system_mnemosyne_tags(text: str, contexts_memory_len: int = 0) -> str:
    """
    使用正则表达式去除LLM上下文系统提示中的<Mnemosyne> </Mnemosyne>标签对。
    如果 contexts_memory_len > 0，则仅保留最后 contexts_memory_len 个标签对。
    """
    if not isinstance(text, str):
        return text  # 如果输入不是字符串，直接返回

    if contexts_memory_len < 0:
        return text

    compiled_regex = re.compile(r"<Mnemosyne>.*?</Mnemosyne>", re.DOTALL)

    if contexts_memory_len == 0:
        cleaned_text = compiled_regex.sub("", text)
    else:
        all_mnemosyne_blocks: list[str] = compiled_regex.findall(text)
        blocks_to_keep: set[str] = set(all_mnemosyne_blocks[-contexts_memory_len:])

        def replace_logic(match: re.Match) -> str:
            block = match.group(0)
            return block if block in blocks_to_keep else ""

        if compiled_regex.search(text):
            cleaned_text = compiled_regex.sub(replace_logic, text)
        else:
            cleaned_text = text

    return cleaned_text


def remove_system_content(
    contents: list[dict[str, str]], contexts_memory_len: int = 0
) -> list[dict[str, str]]:
    """
    从LLM上下文中移除较旧的系统提示 ('role'='system' 的消息)，
    保留指定数量的最新的 system 消息，并维持整体消息顺序。
    """
    if not isinstance(contents, list):
        return []
    if contexts_memory_len < 0:
        return contents

    system_message_indices = [
        i
        for i, msg in enumerate(contents)
        if isinstance(msg, dict) and msg.get("role") == "system"
    ]
    indices_to_remove: set[int] = set()
    num_system_messages = len(system_message_indices)

    if num_system_messages > contexts_memory_len:
        num_to_remove = num_system_messages - contexts_memory_len
        indices_to_remove = set(system_message_indices[:num_to_remove])

    cleaned_contents = [
        msg for i, msg in enumerate(contents) if i not in indices_to_remove
    ]

    return cleaned_contents


def format_context_to_string(
    context_history: list[dict[str, str] | str],
    length: int = 10,
    include_tool_context: bool = False,
    tool_context_limit: int = DEFAULT_TOOL_CONTEXT_LINE_LIMIT,
) -> str:
    """
    从上下文历史记录中提取最后 'length' 条用户和AI的对话消息，
    并将它们的内容转换为用换行符分隔的字符串。
    tool_context_limit 单独限制工具调用上下文，避免挤占普通对话额度。
    """
    if length <= 0:
        return ""

    selected_blocks: list[list[str]] = []
    dialog_count = 0
    tool_count = 0
    tool_context_limit = max(0, int(tool_context_limit))

    for message in reversed(context_history):
        if dialog_count >= length:
            break

        role = None
        content = None

        tool_lines: list[str] = []
        if isinstance(message, dict) and "role" in message:
            role = message.get("role")
            content = message.get("content")
            if include_tool_context:
                if role == "assistant" and message.get("tool_calls"):
                    for tool_call in message.get("tool_calls") or []:
                        tool_lines.append(_format_tool_call_line(tool_call))
                elif role == "tool":
                    call_id = str(message.get("tool_call_id") or "").strip()
                    tool_text = _content_to_safe_text(
                        content, DEFAULT_TOOL_TEXT_MAX_CHARS
                    )
                    if tool_text:
                        if call_id:
                            tool_lines.append(f"tool result id={call_id}: {tool_text}")
                        else:
                            tool_lines.append(f"tool context: {tool_text}")

        block: list[str] = []
        has_dialog_line = False
        if content is not None and role in ("user", "assistant"):
            safe_text = _content_to_safe_text(content)
            if safe_text.strip() and dialog_count < length:
                block.append(f"{role}:{safe_text}\n")
                has_dialog_line = True

        if include_tool_context and tool_lines:
            remaining = tool_context_limit - tool_count
            if remaining > 0:
                selected_tool_lines = tool_lines[:remaining]
                block.extend(line + "\n" for line in selected_tool_lines)
                tool_count += len(selected_tool_lines)

        if not block:
            continue

        selected_blocks.append(block)
        if has_dialog_line:
            dialog_count += 1

    selected_lines: list[str] = []
    for block in reversed(selected_blocks):
        selected_lines.extend(block)

    return "\n".join(selected_lines)


def is_group_chat(event: AstrMessageEvent) -> bool:
    """
    判断消息是否来自群聊。
    """
    return event.get_group_id() != ""


def get_event_platform_id(event: AstrMessageEvent) -> str:
    """
    获取事件平台 ID，优先使用 platform_meta.id，失败时回退到 unified_msg_origin 前缀。
    """
    try:
        platform_meta = getattr(event, "platform_meta", None)
        platform_id = getattr(platform_meta, "id", None)
        if isinstance(platform_id, str) and platform_id.strip():
            return platform_id.strip()
    except Exception:
        pass

    umo = getattr(event, "unified_msg_origin", "")
    if isinstance(umo, str) and ":" in umo:
        return umo.split(":", 1)[0]
    if isinstance(umo, str):
        return umo
    return ""


def extract_query_keywords(text: str, min_token_len: int = 2) -> list[str]:
    """
    从用户查询中提取关键词，用于关键词重排和轻量图谱扩展。
    """
    if not isinstance(text, str) or not text.strip():
        return []

    keywords: list[str] = []
    seen: set[str] = set()

    # 英文/数字词
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", text):
        token_norm = token.lower().strip()
        if len(token_norm) >= max(min_token_len, 3) and token_norm not in seen:
            keywords.append(token_norm)
            seen.add(token_norm)

    # 连续中文片段
    for token in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        token_norm = token.strip()
        if len(token_norm) >= min_token_len and token_norm not in seen:
            keywords.append(token_norm)
            seen.add(token_norm)

    return keywords


def pack_memory_content(content: str, metadata: dict[str, Any] | None) -> str:
    """
    将内部元数据以隐藏标签附加到记忆内容末尾。
    """
    if not isinstance(content, str):
        content = str(content)
    if not isinstance(metadata, dict) or not metadata:
        return content

    try:
        payload = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        return f"{content}\n{MNEMO_META_PREFIX}{payload}{MNEMO_META_SUFFIX}"
    except Exception as e:
        logger.warning(f"附加记忆元数据失败，已回退为纯文本内容: {e}")
        return content


def split_memory_content_meta(content: str) -> tuple[str, dict[str, Any]]:
    """
    从记忆内容中拆分内部元数据。
    """
    if not isinstance(content, str):
        return str(content), {}

    start = content.rfind(MNEMO_META_PREFIX)
    end = content.rfind(MNEMO_META_SUFFIX)
    if start < 0 or end < 0 or end <= start:
        return content, {}

    json_str = content[start + len(MNEMO_META_PREFIX) : end].strip()
    pure_content = content[:start].rstrip()

    try:
        parsed = json.loads(json_str) if json_str else {}
        if isinstance(parsed, dict):
            return pure_content, parsed
    except Exception as e:
        logger.warning(f"解析记忆元数据失败，忽略元数据块: {e}")

    return pure_content, {}


def strip_memory_meta(content: str) -> str:
    """
    移除记忆内容中的内部元数据标签。
    """
    pure_content, _ = split_memory_content_meta(content)
    return pure_content
