# -*- coding: utf-8 -*-
"""
Mnemosyne 插件工具函数
"""

from urllib.parse import urlparse
from astrbot.api.event import AstrMessageEvent
import functools
import re
from typing import List, Dict, Set, Union


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
    实现一个装饰器，将输入的内容全部转化为字符串并打印
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        str_args = [str(arg) for arg in args]
        str_kwargs = {k: str(v) for k, v in kwargs.items()}
        print(
            f"Function '{func.__name__}' called with arguments: args={str_args}, kwargs={str_kwargs}"
        )
        return func(*str_args, **str_kwargs)

    return wrapper


def remove_mnemosyne_tags(
    contents: List[Dict[str, str]], contexts_memory_len: int = 0
) -> List[Dict[str, str]]:
    """
    使用正则表达式去除LLM上下文中的<mnemosyne> </mnemosyne>标签对。
    如果 contexts_memory_len > 0，则仅保留最后 contexts_memory_len 个标签对。

    Args:
        contents: 包含聊天记录的列表，每个元素是一个字典（如 {"role": "user", "content": "..."}）。
        contexts_memory_len: 需要保留的最新的 <mnemosyne> 标签对数量。如果 <= 0，则移除所有标签对。

    Returns:
        清理或部分清理了 <mnemosyne> 标签对的聊天记录列表。
    """
    compiled_regex = re.compile(r"<Mnemosyne>.*?</Mnemosyne>", re.DOTALL)
    cleaned_contents: List[Dict[str, str]] = []

    if contexts_memory_len <= 0:
        # 移除所有标签
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                # 强制转换为字符串
                if not isinstance(original_text, str):
                    original_text = str(original_text)
                cleaned_text = compiled_regex.sub("", original_text)
                cleaned_contents.append({"role": "user", "content": cleaned_text})
            else:
                cleaned_contents.append(content_item)
    else:
        # 找出所有用户消息中的所有 mnemosyne 块
        all_mnemosyne_blocks: List[str] = []
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                # 强制转换为字符串
                if not isinstance(original_text, str):
                    original_text = str(original_text)
                found_blocks = compiled_regex.findall(original_text)
                all_mnemosyne_blocks.extend(found_blocks)

        # 确定要保留的块
        blocks_to_keep: Set[str] = set(all_mnemosyne_blocks[-contexts_memory_len:])

        # 定义替换函数
        def replace_logic(match: re.Match) -> str:
            block = match.group(0)
            return block if block in blocks_to_keep else ""

        # 再次遍历并应用替换逻辑
        for content_item in contents:
            if isinstance(content_item, dict) and content_item.get("role") == "user":
                original_text = content_item.get("content", "")
                # 只有当文本中确实包含需要处理的标签时才进行替换
                # TODO 这里临时处理一下，如果类型是list，直接转换保留
                if isinstance(original_text,list):
                    cleaned_contents.append({"role": "user", "content": original_text})
                if compiled_regex.search(original_text):
                    cleaned_text = compiled_regex.sub(replace_logic, original_text)
                    cleaned_contents.append({"role": "user", "content": cleaned_text})
                else:
                    cleaned_contents.append(content_item)  # 无需处理，直接添加
            else:
                cleaned_contents.append(content_item)

    return cleaned_contents


def remove_system_mnemosyne_tags(text: str, contexts_memory_len: int = 0) -> str:
    """
    使用正则表达式去除LLM上下文系统提示中的<Mnemosyne> </Mnemosyne>标签对。
    如果 contexts_memory_len > 0，则仅保留最后 contexts_memory_len 个标签对。

    Args:
        text: 系统提示字符串。
        contexts_memory_len: 需要保留的最新的 <Mnemosyne> 标签对数量。如果 <= 0，则移除所有标签对。

    Returns:
        清理或部分清理了 <Mnemosyne> 标签对的系统提示字符串。
    """
    if not isinstance(text, str):
        return text  # 如果输入不是字符串，直接返回

    compiled_regex = re.compile(r"<Mnemosyne>.*?</Mnemosyne>", re.DOTALL)

    if contexts_memory_len <= 0:
        # 移除所有标签
        cleaned_text = compiled_regex.sub("", text)
    else:
        # 找出所有 Mnemosyne 块
        all_mnemosyne_blocks: List[str] = compiled_regex.findall(text)

        # 确定要保留的块
        blocks_to_keep: Set[str] = set(all_mnemosyne_blocks[-contexts_memory_len:])

        # 定义替换函数
        def replace_logic(match: re.Match) -> str:
            block = match.group(0)
            return block if block in blocks_to_keep else ""

        # 应用替换逻辑
        # 只有当文本中确实包含需要处理的标签时才进行替换
        if compiled_regex.search(text):
            cleaned_text = compiled_regex.sub(replace_logic, text)
        else:
            cleaned_text = text  # 无需处理

    return cleaned_text


def remove_system_content(
    contents: List[Dict[str, str]], contexts_memory_len: int = 0
) -> List[Dict[str, str]]:
    """
    从LLM上下文中移除较旧的系统提示 ('role'='system' 的消息)，
    保留指定数量的最新的 system 消息，并维持整体消息顺序。

    Args:
        contents: 包含聊天记录的列表。
        contexts_memory_len: 需要保留的最新的 system 消息的数量 (非负整数)。

    Returns:
        处理后的聊天记录列表。
    """
    if not isinstance(contents, list):
        return []
    if contexts_memory_len < 0:
        contexts_memory_len = 0 # 确保为非负数

    # 1. 找到所有 system 消息的索引
    system_message_indices = [
        i for i, msg in enumerate(contents)
        if isinstance(msg, dict) and msg.get("role") == "system"
    ]

    # 2. 确定要移除的 system 消息的索引
    indices_to_remove: Set[int] = set()
    num_system_messages = len(system_message_indices)

    if num_system_messages > contexts_memory_len:

        num_to_remove = num_system_messages - contexts_memory_len

        indices_to_remove = set(system_message_indices[:num_to_remove])

    # 3. 构建新的列表，跳过要移除的索引
    cleaned_contents = [
        msg for i, msg in enumerate(contents)
        if i not in indices_to_remove
    ]

    return cleaned_contents


def format_context_to_string(
    context_history: List[Union[Dict[str, str], str]], length: int = 10
) -> str:
    """
    从上下文历史记录中提取最后 'length' 条用户和AI的对话消息，
    并将它们的内容转换为用换行符分隔的字符串。
    只处理 role 为 'user' 和 'assistant' 的消息，其他类型的消息将被忽略且不计入 'length'。

    Args:
        context_history (list): 上下文历史消息列表，每个消息可以是字典或字符串。
                                如果是字典，应包含 'role' 和 'content' 键。
        length (int, optional): 需要提取的用户或AI对话消息的数量。默认为 10。
                                如果 <= 0，则返回空字符串。

    Returns:
        str: 格式化后的字符串，包含最后 'length' 条 role 为 'user' 和 'assistant'
            的消息内容，消息之间用换行符分隔，按原始顺序排列。
    """
    if length <= 0:
        return ""

    # 使用列表存储符合条件的消息内容，因为我们需要按顺序保留最后N条
    selected_contents: List[str] = []
    count = 0

    # 从后往前遍历历史记录
    for message in reversed(context_history):
        role = None
        content = None

        if isinstance(message, dict) and "role" in message and "content" in message:
            role = message.get("role")
            content = message.get("content")

        # 优化逻辑，添加明确的消息来源
        if content is not None:
            if role == "user":
                selected_contents.insert(0, str("user:" + content + "\n"))
                count += 1
            elif role == "assistant":
                selected_contents.insert(0, str("assistant:" + content + "\n"))
                count += 1
            if count >= length:
                break

    # 使用换行符连接收集到的内容
    return "\n".join(selected_contents)

def is_group_chat(event: AstrMessageEvent) -> bool:
    """
    判断消息是否来自群聊。
    Args:
        event (AstrMessageEvent): 消息事件对象。

    Returns:
        bool: 如果消息来自群聊，则返回True；否则返回False。
    """
    return event.get_group_id() != ""
