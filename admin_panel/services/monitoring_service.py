"""
监控服务 - 提供系统健康检查、性能指标收集等功能
"""

import os
import time
from collections import deque
from datetime import datetime

import psutil

from astrbot.core.log import LogManager

from ..models.monitoring import (
    ComponentHealth,
    ComponentStatus,
    PerformanceMetrics,
    ResourceUsage,
    SystemStatus,
)


class MetricsCollector:
    """指标收集器 - 用于收集和计算性能指标"""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.memory_query_times = deque(maxlen=max_samples)
        self.vector_search_times = deque(maxlen=max_samples)
        self.db_operation_times = deque(maxlen=max_samples)
        self.embedding_api_calls = {"success": 0, "failed": 0}
        self.milvus_api_calls = {"success": 0, "failed": 0}
        self.total_requests = 0
        self.failed_requests = 0

    def record_memory_query(self, duration_ms: float):
        """记录记忆查询时间"""
        self.memory_query_times.append(duration_ms)

    def record_vector_search(self, duration_ms: float):
        """记录向量搜索时间"""
        self.vector_search_times.append(duration_ms)

    def record_db_operation(self, duration_ms: float):
        """记录数据库操作时间"""
        self.db_operation_times.append(duration_ms)

    def record_embedding_api_call(self, success: bool):
        """记录 Embedding API 调用结果"""
        if success:
            self.embedding_api_calls["success"] += 1
        else:
            self.embedding_api_calls["failed"] += 1

    def record_milvus_api_call(self, success: bool):
        """记录 Milvus API 调用结果"""
        if success:
            self.milvus_api_calls["success"] += 1
        else:
            self.milvus_api_calls["failed"] += 1

    def record_request(self, success: bool):
        """记录请求"""
        self.total_requests += 1
        if not success:
            self.failed_requests += 1

    def _calculate_percentile(self, data: deque, percentile: float) -> float:
        """计算百分位数"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def get_metrics(self) -> PerformanceMetrics:
        """获取当前性能指标"""
        metrics = PerformanceMetrics()

        # 计算记忆查询性能
        if self.memory_query_times:
            metrics.memory_query_p50 = self._calculate_percentile(
                self.memory_query_times, 0.50
            )
            metrics.memory_query_p95 = self._calculate_percentile(
                self.memory_query_times, 0.95
            )
            metrics.memory_query_p99 = self._calculate_percentile(
                self.memory_query_times, 0.99
            )

        # 计算向量搜索性能
        if self.vector_search_times:
            metrics.vector_search_p50 = self._calculate_percentile(
                self.vector_search_times, 0.50
            )
            metrics.vector_search_p95 = self._calculate_percentile(
                self.vector_search_times, 0.95
            )
            metrics.vector_search_p99 = self._calculate_percentile(
                self.vector_search_times, 0.99
            )

        # 计算数据库操作性能
        if self.db_operation_times:
            metrics.db_operation_p50 = self._calculate_percentile(
                self.db_operation_times, 0.50
            )
            metrics.db_operation_p95 = self._calculate_percentile(
                self.db_operation_times, 0.95
            )
            metrics.db_operation_p99 = self._calculate_percentile(
                self.db_operation_times, 0.99
            )

        # 计算 API 成功率
        total_embedding = (
            self.embedding_api_calls["success"] + self.embedding_api_calls["failed"]
        )
        if total_embedding > 0:
            metrics.embedding_api_success_rate = (
                self.embedding_api_calls["success"] / total_embedding
            ) * 100

        total_milvus = (
            self.milvus_api_calls["success"] + self.milvus_api_calls["failed"]
        )
        if total_milvus > 0:
            metrics.milvus_api_success_rate = (
                self.milvus_api_calls["success"] / total_milvus
            ) * 100

        # 请求统计
        metrics.total_requests = self.total_requests
        metrics.failed_requests = self.failed_requests

        return metrics


class MonitoringService:
    """监控服务 - 提供系统监控功能"""

    def __init__(self, plugin_instance):
        """
        初始化监控服务

        Args:
            plugin_instance: Mnemosyne 插件实例
        """
        self.plugin = plugin_instance
        self.logger = LogManager.GetLogger(log_name="MonitoringService")
        self.metrics_collector = MetricsCollector()
        self._last_health_check = None
        self._health_check_cache_duration = 30  # 健康检查缓存30秒

    async def get_system_status(self, force_refresh: bool = False) -> SystemStatus:
        """
        获取系统整体状态

        Args:
            force_refresh: 是否强制刷新（忽略缓存）

        Returns:
            SystemStatus: 系统状态对象
        """
        # 检查缓存
        if not force_refresh and self._last_health_check:
            cache_age = (
                datetime.now() - self._last_health_check.timestamp
            ).total_seconds()
            if cache_age < self._health_check_cache_duration:
                return self._last_health_check

        components = {}
        overall_healthy = True

        # 检查 Milvus 连接
        milvus_health = await self._check_milvus_health()
        components["milvus"] = milvus_health
        if milvus_health.status != ComponentStatus.HEALTHY:
            overall_healthy = False

        # 检查 Embedding API
        embedding_health = await self._check_embedding_health()
        components["embedding_api"] = embedding_health
        if embedding_health.status != ComponentStatus.HEALTHY:
            overall_healthy = False

        # 检查 MessageCounter
        counter_health = await self._check_message_counter_health()
        components["message_counter"] = counter_health
        if counter_health.status != ComponentStatus.HEALTHY:
            overall_healthy = False

        # 检查后台任务
        task_health = await self._check_background_task_health()
        components["background_task"] = task_health
        if task_health.status != ComponentStatus.HEALTHY:
            overall_healthy = False

        # 确定整体状态
        if not overall_healthy:
            # 检查是否有任何 UNHEALTHY 组件
            has_unhealthy = any(
                c.status == ComponentStatus.UNHEALTHY for c in components.values()
            )
            overall_status = (
                ComponentStatus.UNHEALTHY if has_unhealthy else ComponentStatus.DEGRADED
            )
        else:
            overall_status = ComponentStatus.HEALTHY

        status = SystemStatus(overall_status=overall_status, components=components)

        self._last_health_check = status
        return status

    async def _check_milvus_health(self) -> ComponentHealth:
        """检查 Milvus 健康状态"""
        try:
            if not self.plugin.milvus_manager:
                return ComponentHealth(
                    name="milvus",
                    status=ComponentStatus.UNHEALTHY,
                    message="Milvus 管理器未初始化",
                )

            if not self.plugin.milvus_manager.is_connected():
                return ComponentHealth(
                    name="milvus",
                    status=ComponentStatus.UNHEALTHY,
                    message="未连接到 Milvus",
                )

            # 获取集合数量
            collections = self.plugin.milvus_manager.list_collections()

            return ComponentHealth(
                name="milvus",
                status=ComponentStatus.HEALTHY,
                message="Milvus 运行正常",
                metadata={"collections_count": len(collections)},
            )
        except Exception as e:
            self.logger.error(f"检查 Milvus 健康状态失败: {e}")
            return ComponentHealth(
                name="milvus",
                status=ComponentStatus.UNHEALTHY,
                message=f"检查失败: {str(e)}",
            )

    async def _check_embedding_health(self) -> ComponentHealth:
       """检查 Embedding API 健康状态"""
       try:
           if not self.plugin.embedding_provider:
               return ComponentHealth(
                   name="embedding_api",
                   status=ComponentStatus.UNHEALTHY,
                   message="Embedding 服务未初始化",
               )

           # 简单的连接测试
           # 注意：这里不进行实际的API调用以避免产生费用
           return ComponentHealth(
               name="embedding_api",
               status=ComponentStatus.HEALTHY,
               message="Embedding API 已配置",
           )
       except Exception as e:
           self.logger.error(f"检查 Embedding API 健康状态失败: {e}")
           return ComponentHealth(
               name="embedding_api",
               status=ComponentStatus.UNHEALTHY,
               message=f"检查失败: {str(e)}",
           )

    async def _check_message_counter_health(self) -> ComponentHealth:
        """检查 MessageCounter 健康状态"""
        try:
            if not self.plugin.msg_counter:
                return ComponentHealth(
                    name="message_counter",
                    status=ComponentStatus.UNHEALTHY,
                    message="MessageCounter 未初始化",
                )

            # 测试数据库连接
            self.plugin.msg_counter.get_counter("_health_check_")

            return ComponentHealth(
                name="message_counter",
                status=ComponentStatus.HEALTHY,
                message="MessageCounter 运行正常",
            )
        except Exception as e:
            self.logger.error(f"检查 MessageCounter 健康状态失败: {e}")
            return ComponentHealth(
                name="message_counter",
                status=ComponentStatus.UNHEALTHY,
                message=f"检查失败: {str(e)}",
            )

    async def _check_background_task_health(self) -> ComponentHealth:
        """检查后台任务健康状态"""
        try:
            if not hasattr(self.plugin, "_summary_check_task"):
                return ComponentHealth(
                    name="background_task",
                    status=ComponentStatus.UNKNOWN,
                    message="后台任务未配置",
                )

            task = self.plugin._summary_check_task
            if not task:
                return ComponentHealth(
                    name="background_task",
                    status=ComponentStatus.UNKNOWN,
                    message="后台任务未启动",
                )

            if task.done():
                try:
                    task.result()
                    return ComponentHealth(
                        name="background_task",
                        status=ComponentStatus.DEGRADED,
                        message="后台任务已完成（不应该发生）",
                    )
                except Exception as e:
                    return ComponentHealth(
                        name="background_task",
                        status=ComponentStatus.UNHEALTHY,
                        message=f"后台任务失败: {str(e)}",
                    )

            return ComponentHealth(
                name="background_task",
                status=ComponentStatus.HEALTHY,
                message="后台任务运行中",
            )
        except Exception as e:
            self.logger.error(f"检查后台任务健康状态失败: {e}")
            return ComponentHealth(
                name="background_task",
                status=ComponentStatus.UNHEALTHY,
                message=f"检查失败: {str(e)}",
            )

    def get_performance_metrics(self) -> PerformanceMetrics:
        """获取性能指标"""
        return self.metrics_collector.get_metrics()

    async def get_resource_usage(self) -> ResourceUsage:
        """获取资源使用情况"""
        usage = ResourceUsage()

        try:
            # 获取进程内存使用
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            usage.memory_used_mb = memory_info.rss / 1024 / 1024

            # 获取系统内存限制
            virtual_memory = psutil.virtual_memory()
            usage.memory_limit_mb = virtual_memory.total / 1024 / 1024

        except Exception as e:
            self.logger.error(f"获取内存信息失败: {e}")

        try:
            # 获取数据库大小
            if self.plugin.msg_counter:
                db_file = self.plugin.msg_counter.db_file
                if os.path.exists(db_file):
                    usage.db_size_mb = os.path.getsize(db_file) / 1024 / 1024
        except Exception as e:
            self.logger.error(f"获取数据库大小失败: {e}")

        try:
            # 获取向量数据库统计
            if self.plugin.milvus_manager and self.plugin.milvus_manager.is_connected():
                collections = self.plugin.milvus_manager.list_collections()
                usage.vector_db_collections = len(collections)

                # 获取当前集合的记录数
                if self.plugin.milvus_manager.has_collection(
                    self.plugin.collection_name
                ):
                    collection = self.plugin.milvus_manager.get_collection(
                        self.plugin.collection_name
                    )
                    usage.vector_db_total_records = collection.num_entities
        except Exception as e:
            self.logger.error(f"获取向量数据库统计失败: {e}")

        try:
            # 获取活跃会话数
            if self.plugin.context_manager:
                usage.total_sessions = len(self.plugin.context_manager.conversations)
                # 假设最近有消息的会话为活跃会话（过去1小时）
                now = time.time()
                active_count = 0
                for (
                    session_id,
                    conv_data,
                ) in self.plugin.context_manager.conversations.items():
                    last_time = conv_data.get("last_summary_time", 0)
                    if now - last_time < 3600:  # 1小时内
                        active_count += 1
                usage.active_sessions = active_count
        except Exception as e:
            self.logger.error(f"获取会话统计失败: {e}")

        try:
            # 获取后台任务状态
            if (
                hasattr(self.plugin, "_summary_check_task")
                and self.plugin._summary_check_task
            ):
                task = self.plugin._summary_check_task
                if not task.done():
                    usage.background_tasks_running = 1
                elif task.done():
                    try:
                        task.result()
                    except Exception:
                        usage.background_tasks_failed = 1
        except Exception as e:
            self.logger.error(f"获取后台任务状态失败: {e}")

        return usage

    def record_operation_time(self, operation_type: str, duration_ms: float):
        """
        记录操作时间

        Args:
            operation_type: 操作类型 (memory_query, vector_search, db_operation)
            duration_ms: 持续时间（毫秒）
        """
        if operation_type == "memory_query":
            self.metrics_collector.record_memory_query(duration_ms)
        elif operation_type == "vector_search":
            self.metrics_collector.record_vector_search(duration_ms)
        elif operation_type == "db_operation":
            self.metrics_collector.record_db_operation(duration_ms)
