# -*- coding: utf-8 -*-
"""
监控相关路由
提供系统状态、性能指标、资源使用等 API
"""

from typing import Dict, Any
from astrbot.core.log import LogManager
from ..services.monitoring_service import MonitoringService
from ..middleware.auth import create_auth_middleware

logger = LogManager.GetLogger(log_name="MonitoringRoutes")


def setup_monitoring_routes(app, plugin_instance):
    """
    设置监控相关路由（强制认证）
    
    注意：这里的路由实现是一个示例框架
    实际使用时需要根据 AstrBot 的 Web 框架进行适配
    
    Args:
        app: Web 应用实例
        plugin_instance: Mnemosyne 插件实例
    """
    monitoring_service = MonitoringService(plugin_instance)
    
    # 创建认证中间件
    api_key = plugin_instance.config.get("admin_panel", {}).get("api_key")
    auth = create_auth_middleware(api_key)
    
    # API: 获取系统状态（需要认证）
    @auth.require_auth
    async def get_system_status(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        GET /api/monitoring/status
        获取系统整体状态
        
        Query Parameters:
            - force_refresh: bool, 是否强制刷新缓存
        
        Returns:
            {
                "success": true,
                "data": {
                    "overall_status": "healthy",
                    "components": {...},
                    "timestamp": "2025-10-24T11:20:00"
                }
            }
        """
        try:
            force_refresh = request.get('force_refresh', False)
            status = await monitoring_service.get_system_status(force_refresh=force_refresh)
            
            return {
                "success": True,
                "data": status.to_dict()
            }
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 获取性能指标（需要认证）
    @auth.require_auth
    async def get_performance_metrics(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        GET /api/monitoring/metrics
        获取性能指标
        
        Returns:
            {
                "success": true,
                "data": {
                    "memory_query": {"p50": 10.5, "p95": 50.2, "p99": 100.5},
                    "vector_search": {...},
                    "db_operation": {...},
                    "api_success_rate": {...},
                    "requests": {...}
                }
            }
        """
        try:
            metrics = monitoring_service.get_performance_metrics()
            
            return {
                "success": True,
                "data": metrics.to_dict()
            }
        except Exception as e:
            logger.error(f"获取性能指标失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 获取资源使用情况（需要认证）
    @auth.require_auth
    async def get_resource_usage(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        GET /api/monitoring/resources
        获取资源使用情况
        
        Returns:
            {
                "success": true,
                "data": {
                    "memory": {"used_mb": 128.5, "limit_mb": 2048, "usage_percent": 6.3},
                    "database": {"size_mb": 10.2},
                    "vector_database": {...},
                    "sessions": {...},
                    "background_tasks": {...}
                }
            }
        """
        try:
            usage = await monitoring_service.get_resource_usage()
            
            return {
                "success": True,
                "data": usage.to_dict()
            }
        except Exception as e:
            logger.error(f"获取资源使用情况失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 获取完整仪表板数据（需要认证）
    @auth.require_auth
    async def get_dashboard_data(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        GET /api/monitoring/dashboard
        获取完整的仪表板数据（包含状态、指标、资源）
        
        Returns:
            {
                "success": true,
                "data": {
                    "status": {...},
                    "metrics": {...},
                    "resources": {...}
                }
            }
        """
        try:
            status = await monitoring_service.get_system_status()
            metrics = monitoring_service.get_performance_metrics()
            resources = await monitoring_service.get_resource_usage()
            
            return {
                "success": True,
                "data": {
                    "status": status.to_dict(),
                    "metrics": metrics.to_dict(),
                    "resources": resources.to_dict()
                }
            }
        except Exception as e:
            logger.error(f"获取仪表板数据失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # 注册路由到应用
    # 注意：这里是伪代码，需要根据实际的 Web 框架进行适配
    # 例如 Flask: app.route('/api/monitoring/status', methods=['GET'])(get_system_status)
    # 例如 FastAPI: app.get('/api/monitoring/status')(get_system_status)
    
    routes = {
        '/api/monitoring/status': get_system_status,
        '/api/monitoring/metrics': get_performance_metrics,
        '/api/monitoring/resources': get_resource_usage,
        '/api/monitoring/dashboard': get_dashboard_data,
    }
    
    logger.info(f"监控路由已注册: {list(routes.keys())}")
    
    return routes