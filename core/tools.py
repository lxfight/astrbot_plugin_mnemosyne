# -*- coding: utf-8 -*-
"""
Mnemosyne 插件工具函数
"""

from urllib.parse import urlparse

def parse_address(address: str):
    """
    解析地址，提取出主机名和端口号。
    如果地址没有协议前缀，则默认添加 "http://"
    """
    if not (address.startswith("http://") or address.startswith("https://")):
        address = "http://" + address
    parsed = urlparse(address)
    host = parsed.hostname
    port = parsed.port if parsed.port is not None else 19530  # 如果未指定端口，默认使用19530
    return host, port