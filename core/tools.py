"""Mnemosyne 插件工具函数
"""

import functools
import re
from typing import Any
from urllib.parse import urlparse

from astrbot.api.event import AstrMessageEvent
from astrbot.core.log import LogManager

logger = LogManager.GetLogger(__name__)


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

    if contexts_memory_len == 0:
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                # 关键修复：多模态内容（list/dict 等）不能强制转换为字符串。
                # 只有在 content 为 str 时才需要清理标签。
                if isinstance(original_text, str):
                    cleaned_text = compiled_regex.sub("", original_text)
                    cleaned_contents.append({"role": "user", "content": cleaned_text})
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
                    cleaned_contents.append({"role": "user", "content": original_text})
                elif isinstance(original_text, str):
                    # 2. 如果内容是字符串，检查是否需要清理标签
                    if compiled_regex.search(original_text):
                        # 内容包含标签，进行清理
                        cleaned_text = compiled_regex.sub(replace_logic, original_text)
                        cleaned_contents.append(
                            {"role": "user", "content": cleaned_text}
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
    context_history: list[dict[str, str] | str], length: int = 10
) -> str:
    """
    从上下文历史记录中提取最后 'length' 条用户和AI的对话消息，
    并将它们的内容转换为用换行符分隔的字符串。
    """
    if length <= 0:
        return ""

    def _truncate_text(text: str, max_chars: int = 2000) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "…(truncated)"

    def _content_to_safe_text(content: Any) -> str:
        """将 AstrBot/OpenAI 风格上下文内容安全转为文本。

        精确依据 AstrBot 源码结构：
        - `content` 可能是 `str`
        - 或 `list[dict]`，元素为 ContentPart，常见 `type`: text/image_url/audio_url/think
          其中图片真实数据在 `image_url.url` (data:image/...;base64,...)，绝不能展开。
        """

        # 1) 纯文本
        if isinstance(content, str):
            # 保险：若出现 data-url/base64 直接降级为占位符
            if content.startswith("base64://") or content.startswith("data:image"):
                return "[图片]"
            return _truncate_text(content)

        # 2) OpenAI 多模态 content blocks
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")

                # AstrBot/OpenAI: {"type": "text", "text": "..."}
                if item_type == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(_truncate_text(text))
                    continue

                # AstrBot/OpenAI: {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}
                # openai_source 的实现也会用 `"image_url" in item` 来判断，因此这里双保险。
                if item_type == "image_url" or "image_url" in item:
                    parts.append("[图片]")
                    continue

                # AstrBot: {"type": "audio_url", "audio_url": {"url": "data:audio/...;base64,..."}}
                if item_type == "audio_url" or "audio_url" in item:
                    parts.append("[音频]")
                    continue

                # assistant content 可能包含 think part；总结/记忆无需包含
                if item_type == "think":
                    continue

                # 其他 ContentPart：不展开 payload，给占位
                if isinstance(item_type, str) and item_type:
                    parts.append(f"[{item_type}]")

            merged = " ".join(p for p in parts if p)
            return merged or ""

        # 3) 其他结构：避免展开潜在大对象
        if isinstance(content, dict):
            if "image_url" in content or "audio_url" in content:
                return "[图片]" if "image_url" in content else "[音频]"
            text = content.get("text")
            if isinstance(text, str):
                return _truncate_text(text)
            return ""

        return ""

    selected_contents: list[str] = []
    count = 0

    for message in reversed(context_history):
        if count >= length:
            break

        role = None
        content = None

        if isinstance(message, dict) and "role" in message and "content" in message:
            role = message.get("role")
            content = message.get("content")

        if content is not None:
            safe_text = _content_to_safe_text(content)
            if role == "user":
                selected_contents.insert(0, "user:" + safe_text + "\n")
                count += 1
            elif role == "assistant":
                selected_contents.insert(0, "assistant:" + safe_text + "\n")
                count += 1

    return "\n".join(selected_contents)


def is_group_chat(event: AstrMessageEvent) -> bool:
    """
    判断消息是否来自群聊。
    """
    return event.get_group_id() != ""
