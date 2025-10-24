# -*- coding: utf-8 -*-
"""
Mnemosyne 插件工具函数
"""

import functools
import re
from typing import List, Dict, Set, Union
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
    contents: List[Dict[str, str]], contexts_memory_len: int = 0
) -> List[Dict[str, str]]:
    """
    使用正则表达式去除LLM上下文中的<mnemosyne> </mnemosyne>标签对。
    - contexts_memory_len > 0: 保留最新的N个标签对。
    - contexts_memory_len == 0: 移除所有标签对。
    - contexts_memory_len < 0: 保留所有标签对，不作任何删除。
    """
    if contexts_memory_len < 0:
        return contents

    compiled_regex = re.compile(r"<Mnemosyne>.*?</Mnemosyne>", re.DOTALL)
    cleaned_contents: List[Dict[str, str]] = []

    if contexts_memory_len == 0:
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                if not isinstance(original_text, str):
                    original_text = str(original_text)
                cleaned_text = compiled_regex.sub("", original_text)
                cleaned_contents.append({"role": "user", "content": cleaned_text})
            else:
                cleaned_contents.append(content_item)
    else:  # contexts_memory_len > 0
        all_mnemosyne_blocks: List[str] = []
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                if isinstance(original_text, str):
                    found_blocks = compiled_regex.findall(original_text)
                    all_mnemosyne_blocks.extend(found_blocks)

        blocks_to_keep: Set[str] = set(all_mnemosyne_blocks[-contexts_memory_len:])

        def replace_logic(match: re.Match) -> str:
            block = match.group(0)
            return block if block in blocks_to_keep else ""

        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                
                # --- 【核心修改】将独立的 if 改为 elif，形成互斥逻辑 ---
                if isinstance(original_text, list):
                    # 1. 如果是列表，直接添加，然后处理下一个条目
                    cleaned_contents.append({"role": "user", "content": original_text})
                elif compiled_regex.search(original_text):
                    # 2. 否则，如果内容匹配正则，则进行清理后添加
                    cleaned_text = compiled_regex.sub(replace_logic, original_text)
                    cleaned_contents.append({"role": "user", "content": cleaned_text})
                else:
                    # 3. 否则 (既不是列表，也不匹配正则)，直接添加原始条目
                    cleaned_contents.append(content_item)
            else:
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
        all_mnemosyne_blocks: List[str] = compiled_regex.findall(text)
        blocks_to_keep: Set[str] = set(all_mnemosyne_blocks[-contexts_memory_len:])

        def replace_logic(match: re.Match) -> str:
            block = match.group(0)
            return block if block in blocks_to_keep else ""

        if compiled_regex.search(text):
            cleaned_text = compiled_regex.sub(replace_logic, text)
        else:
            cleaned_text = text

    return cleaned_text


def remove_system_content(
    contents: List[Dict[str, str]], contexts_memory_len: int = 0
) -> List[Dict[str, str]]:
    """
    从LLM上下文中移除较旧的系统提示 ('role'='system' 的消息)，
    保留指定数量的最新的 system 消息，并维持整体消息顺序。
    """
    if not isinstance(contents, list):
        return []
    if contexts_memory_len < 0:
        return contents

    system_message_indices = [
        i for i, msg in enumerate(contents)
        if isinstance(msg, dict) and msg.get("role") == "system"
    ]
    indices_to_remove: Set[int] = set()
    num_system_messages = len(system_message_indices)

    if num_system_messages > contexts_memory_len:
        num_to_remove = num_system_messages - contexts_memory_len
        indices_to_remove = set(system_message_indices[:num_to_remove])

    cleaned_contents = [
        msg for i, msg in enumerate(contents) if i not in indices_to_remove
    ]

    return cleaned_contents


def format_context_to_string(
    context_history: List[Union[Dict[str, str], str]], length: int = 10
) -> str:
    """
    从上下文历史记录中提取最后 'length' 条用户和AI的对话消息，
    并将它们的内容转换为用换行符分隔的字符串。
    """
    if length <= 0:
        return ""

    selected_contents: List[str] = []
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
            if role == "user":
                selected_contents.insert(0, str("user:" + str(content) + "\n"))
                count += 1
            elif role == "assistant":
                selected_contents.insert(0, str("assistant:" + str(content) + "\n"))
                count += 1

    return "\n".join(selected_contents)


def is_group_chat(event: AstrMessageEvent) -> bool:
    """
    判断消息是否来自群聊。
    """
    return event.get_group_id() != ""
