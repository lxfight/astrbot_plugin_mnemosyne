# -*- coding: utf-8 -*-
"""
Admin Panel 路由层
"""

from .monitoring import setup_monitoring_routes
from .memory import setup_memory_routes

__all__ = [
    'setup_monitoring_routes',
    'setup_memory_routes',
]


def setup_all_routes(app, plugin_instance):
    """
    设置所有路由
    
    Args:
        app: Web 应用实例
        plugin_instance: Mnemosyne 插件实例
    """
    setup_monitoring_routes(app, plugin_instance)
    setup_memory_routes(app, plugin_instance)