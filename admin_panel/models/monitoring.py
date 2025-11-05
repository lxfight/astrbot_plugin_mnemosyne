"""
监控相关数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ComponentStatus(str, Enum):
    """组件状态枚举"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """单个组件的健康状态"""

    name: str
    status: ComponentStatus
    message: str | None = None
    last_check: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class SystemStatus:
    """系统整体状态"""

    overall_status: ComponentStatus
    components: dict[str, ComponentHealth]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "overall_status": self.overall_status.value,
            "components": {
                name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "last_check": comp.last_check.isoformat(),
                    "metadata": comp.metadata,
                }
                for name, comp in self.components.items()
            },
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PerformanceMetrics:
    """性能指标"""

    # 查询性能
    memory_query_p50: float = 0.0  # 毫秒
    memory_query_p95: float = 0.0
    memory_query_p99: float = 0.0

    # 向量检索性能
    vector_search_p50: float = 0.0
    vector_search_p95: float = 0.0
    vector_search_p99: float = 0.0

    # 数据库操作性能
    db_operation_p50: float = 0.0
    db_operation_p95: float = 0.0
    db_operation_p99: float = 0.0

    # API 调用成功率
    embedding_api_success_rate: float = 100.0  # 百分比
    milvus_api_success_rate: float = 100.0

    # 请求统计
    total_requests: int = 0
    failed_requests: int = 0

    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "memory_query": {
                "p50": self.memory_query_p50,
                "p95": self.memory_query_p95,
                "p99": self.memory_query_p99,
            },
            "vector_search": {
                "p50": self.vector_search_p50,
                "p95": self.vector_search_p95,
                "p99": self.vector_search_p99,
            },
            "db_operation": {
                "p50": self.db_operation_p50,
                "p95": self.db_operation_p95,
                "p99": self.db_operation_p99,
            },
            "api_success_rate": {
                "embedding": self.embedding_api_success_rate,
                "milvus": self.milvus_api_success_rate,
            },
            "requests": {
                "total": self.total_requests,
                "failed": self.failed_requests,
                "success_rate": (self.total_requests - self.failed_requests)
                / self.total_requests
                * 100
                if self.total_requests > 0
                else 100.0,
            },
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ResourceUsage:
    """资源使用情况"""

    # 内存占用
    memory_used_mb: float = 0.0
    memory_limit_mb: float | None = None

    # 数据库大小
    db_size_mb: float = 0.0

    # 向量数据库统计
    vector_db_collections: int = 0
    vector_db_total_records: int = 0
    vector_db_size_mb: float = 0.0

    # 活跃会话
    active_sessions: int = 0
    total_sessions: int = 0

    # 后台任务
    background_tasks_running: int = 0
    background_tasks_failed: int = 0

    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转换为字典"""
        memory_usage_percent = (
            (self.memory_used_mb / self.memory_limit_mb * 100)
            if self.memory_limit_mb
            else None
        )

        return {
            "memory": {
                "used_mb": round(self.memory_used_mb, 2),
                "limit_mb": round(self.memory_limit_mb, 2)
                if self.memory_limit_mb
                else None,
                "usage_percent": round(memory_usage_percent, 2)
                if memory_usage_percent
                else None,
            },
            "database": {"size_mb": round(self.db_size_mb, 2)},
            "vector_database": {
                "collections": self.vector_db_collections,
                "total_records": self.vector_db_total_records,
                "size_mb": round(self.vector_db_size_mb, 2),
            },
            "sessions": {"active": self.active_sessions, "total": self.total_sessions},
            "background_tasks": {
                "running": self.background_tasks_running,
                "failed": self.background_tasks_failed,
            },
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BackgroundTaskStatus:
    """后台任务状态"""

    task_name: str
    is_running: bool
    last_execution_time: datetime | None = None
    last_success_time: datetime | None = None
    error_count: int = 0
    last_error: str | None = None
    total_executions: int = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "task_name": self.task_name,
            "is_running": self.is_running,
            "last_execution_time": self.last_execution_time.isoformat()
            if self.last_execution_time
            else None,
            "last_success_time": self.last_success_time.isoformat()
            if self.last_success_time
            else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "total_executions": self.total_executions,
        }
