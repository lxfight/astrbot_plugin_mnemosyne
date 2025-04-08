# -*- coding: utf-8 -*-
"""
Mnemosyne 插件工具函数
"""

from urllib.parse import urlparse
import functools
import re


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


def remove_mnemosyne_tags(contents: list):
    """
    使用正则表达式去除LLM上下文中的<mnemosyne> </mnemosyne>标签对
    """
    compiled_regex = re.compile(r"<mnemosyne>.*?</mnemosyne>", re.DOTALL)
    cleaned_contents = []
    for content in contents:
        if isinstance(content, dict) and content.get("role") == "user":
            cleaned_text = compiled_regex.sub("", content.get("content", ""))
            cleaned_contents.append({"role": "user", "content": cleaned_text})
        else:
            cleaned_contents.append(content)

    return cleaned_contents


def remove_system_mnemosyne_tags(text: str):
    """
    使用正则表达式去除LLM上下文系统提示中的<mnemosyne> </mnemosyne>标签对
    """
    compiled_regex = re.compile(r"<mnemosyne>.*?</mnemosyne>", re.DOTALL)
    if isinstance(text, str):
        cleaned_text = compiled_regex.sub("", text)
        return cleaned_text
    return text


def remove_system_content(contents: list):
    """
    使用正则表达式去除LLM上下文中插入的系统提示
    """
    cleaned_contents = []
    for content in contents:
        if isinstance(content, dict) and content.get("role") == "system":
            # 如果是字典且 role 是 system，则跳过，不添加到 cleaned_contents
            continue
        else:
            cleaned_contents.append(
                content
            )  # 保留其他类型的消息或非 system role 的消息
    return cleaned_contents


def format_context_to_string(context_history: list) -> str:
    """
    将字典列表形式的上下文历史记录转换为字符串，
    只保留 role 为 'user' 和 'assistant' 的消息内容，并用换行符分隔。

    Args:
        context_history (list): 上下文历史消息列表，每个消息可以是字典或字符串。
                                如果是字典，应包含 'role' 和 'content' 键。

    Returns:
        str: 格式化后的字符串，包含 role 为 'user' 和 'assistant' 的消息内容，
            消息之间用换行符分隔。
    """
    formatted_string = ""
    for message in context_history:
        if isinstance(message, dict) and "role" in message and "content" in message:
            role = message["role"]
            content = message["content"]
            if role == "user" or role == "assistant":
                formatted_string += content + "\n"  # 使用换行符分隔消息
        elif isinstance(message, str):
            # 如果消息是字符串，直接添加到字符串中，并假设是用户或助手消息，也用换行符分隔
            formatted_string += message + "\n"
        # 忽略其他类型的消息或 role 不是 user/assistant 的字典消息

    return formatted_string.strip()  # 使用 strip() 移除末尾可能多余的换行符
