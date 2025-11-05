"""
监控相关路由
提供系统状态、性能指标、资源使用等 API
"""

from fastapi import APIRouter, HTTPException, Query, Request

from astrbot.core.log import LogManager

from ..services.monitoring_service import MonitoringService

logger = LogManager.GetLogger(log_name="MonitoringRoutes")


def setup_monitoring_routes(app, plugin_instance):
    """
    设置监控相关路由（强制认证）

    Args:
        app: Web 应用实例
        plugin_instance: Mnemosyne 插件实例
    """
    monitoring_service = MonitoringService(plugin_instance)
    router = APIRouter()

    # API: 获取系统状态
    @router.get("/api/monitoring/status")
    async def get_system_status(
        request: Request, force_refresh: bool = Query(default=False)
    ):
        try:
            status = await monitoring_service.get_system_status(
                force_refresh=force_refresh
            )
            return status.to_dict()
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # API: 获取性能指标
    @router.get("/api/monitoring/metrics")
    async def get_performance_metrics(request: Request):
        try:
            metrics = monitoring_service.get_performance_metrics()
            return metrics.to_dict()
        except Exception as e:
            logger.error(f"获取性能指标失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # API: 获取资源使用情况
    @router.get("/api/monitoring/resources")
    async def get_resource_usage(request: Request):
        try:
            usage = await monitoring_service.get_resource_usage()
            return usage.to_dict()
        except Exception as e:
            logger.error(f"获取资源使用情况失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # API: 获取完整仪表板数据
    @router.get("/api/monitoring/dashboard")
    async def get_dashboard_data(request: Request):
        try:
            status = await monitoring_service.get_system_status()
            metrics = monitoring_service.get_performance_metrics()
            resources = await monitoring_service.get_resource_usage()

            return {
                "status": status.to_dict(),
                "metrics": metrics.to_dict(),
                "resources": resources.to_dict(),
            }
        except Exception as e:
            logger.error(f"获取仪表板数据失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # 将路由器包含到主应用中
    app.include_router(router)

    logger.info("监控路由已注册")
