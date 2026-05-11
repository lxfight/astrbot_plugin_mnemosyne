"""
Mnemosyne 插件 AstrBot Pages Web API handlers。

响应格式说明：
- 成功: 直接返回数据体（Dashboard 会自动提取 .data 字段）
- 失败: 返回 {"status": "error", "message": "错误信息"}
- 文件下载: 返回 Quart Response 对象（Content-Disposition: attachment）
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any

from astrbot.api import logger
from quart import Response, jsonify, request

from .admin_panel.models.memory import MemorySearchRequest
from .admin_panel.services.memory_service import MemoryService
from .admin_panel.services.monitoring_service import MonitoringService

PLUGIN_NAME = "astrbot_plugin_mnemosyne"


class MnemosyneWebApi:
    """Mnemosyne 插件 Pages Web API 处理器"""

    def __init__(self, plugin) -> None:
        self.plugin = plugin
        self.memory_service = MemoryService(plugin)
        self.monitoring_service = MonitoringService(plugin)

    def register_routes(self) -> None:
        register = self.plugin.context.register_web_api

        # --- 监控 API ---
        register(f"/{PLUGIN_NAME}/monitoring/dashboard", self.get_dashboard_data, ["GET"], "")
        register(f"/{PLUGIN_NAME}/monitoring/status", self.get_system_status, ["GET"], "")
        register(f"/{PLUGIN_NAME}/monitoring/metrics", self.get_performance_metrics, ["GET"], "")
        register(f"/{PLUGIN_NAME}/monitoring/resources", self.get_resource_usage, ["GET"], "")

        # --- 记忆管理 API ---
        register(f"/{PLUGIN_NAME}/memories/search", self.search_memories, ["GET", "POST"], "")
        register(f"/{PLUGIN_NAME}/memories/statistics", self.get_memory_statistics, ["GET"], "")
        register(f"/{PLUGIN_NAME}/memories/sessions", self.get_session_list, ["GET"], "")
        register(f"/{PLUGIN_NAME}/memories/delete", self.batch_delete_memories, ["POST"], "")
        register(f"/{PLUGIN_NAME}/memories/<memory_id>/delete", self.delete_single_memory, ["POST"], "")
        register(f"/{PLUGIN_NAME}/memories/session/<session_id>/delete", self.delete_session_memories, ["POST"], "")
        register(f"/{PLUGIN_NAME}/memories/export", self.export_memories, ["GET"], "")
        register(f"/{PLUGIN_NAME}/memories/vector-search", self.vector_search_memories, ["POST"], "")

        # --- 配置 API ---
        register(f"/{PLUGIN_NAME}/config", self.get_config, ["GET"], "")
        register(f"/{PLUGIN_NAME}/config", self.update_config, ["POST"], "")

    def _error(self, message: str) -> dict:
        return {"status": "error", "message": message}

    # ==================== 监控 API ====================

    async def get_dashboard_data(self) -> Any:
        try:
            status = await self.monitoring_service.get_system_status()
            metrics = self.monitoring_service.get_performance_metrics()
            resources = await self.monitoring_service.get_resource_usage()
            return jsonify({
                "status": status.to_dict(),
                "metrics": metrics.to_dict(),
                "resources": resources.to_dict(),
            })
        except Exception as e:
            logger.error(f"获取仪表板数据失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def get_system_status(self) -> Any:
        try:
            force_refresh = request.args.get("force_refresh", "false").lower() == "true"
            status = await self.monitoring_service.get_system_status(force_refresh=force_refresh)
            return jsonify(status.to_dict())
        except Exception as e:
            logger.error(f"获取系统状态失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def get_performance_metrics(self) -> Any:
        try:
            metrics = self.monitoring_service.get_performance_metrics()
            return jsonify(metrics.to_dict())
        except Exception as e:
            logger.error(f"获取性能指标失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def get_resource_usage(self) -> Any:
        try:
            usage = await self.monitoring_service.get_resource_usage()
            return jsonify(usage.to_dict())
        except Exception as e:
            logger.error(f"获取资源使用情况失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    # ==================== 记忆管理 API ====================

    async def search_memories(self) -> Any:
        try:
            session_id = request.args.get("session_id") or None
            keyword = request.args.get("keyword") or None
            persona_id = request.args.get("persona_id") or None
            start_date = request.args.get("start_date") or None
            end_date = request.args.get("end_date") or None

            try:
                limit = int(request.args.get("limit", "10"))
                limit = max(1, min(limit, 100))
            except (ValueError, TypeError):
                limit = 10

            try:
                offset = int(request.args.get("offset", "0"))
                offset = max(0, offset)
            except (ValueError, TypeError):
                offset = 0

            sort_by = request.args.get("sort_by", "create_time")
            sort_order = request.args.get("sort_order", "desc")

            start_datetime = datetime.fromisoformat(start_date) if start_date else None
            end_datetime = datetime.fromisoformat(end_date) if end_date else None

            search_req = MemorySearchRequest(
                session_id=session_id, keyword=keyword,
                start_date=start_datetime, end_date=end_datetime,
                persona_id=persona_id, limit=limit, offset=offset,
                sort_by=sort_by, sort_order=sort_order,
            )
            response = await self.memory_service.search_memories(search_req)
            return jsonify(response.to_dict())
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def get_memory_statistics(self) -> Any:
        try:
            stats = await self.memory_service.get_memory_statistics()
            return jsonify(stats.to_dict())
        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def get_session_list(self) -> Any:
        try:
            try:
                limit = int(request.args.get("limit", "100"))
                limit = max(1, min(limit, 1000))
            except (ValueError, TypeError):
                limit = 100
            sessions = await self.memory_service.get_session_list(limit=limit)
            return jsonify(sessions)
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def batch_delete_memories(self) -> Any:
        try:
            body = await request.get_json(silent=True) or {}
            memory_ids = body.get("memory_ids", [])
            if not memory_ids or not isinstance(memory_ids, list):
                return jsonify(self._error("memory_ids 参数无效"))

            for mid in memory_ids:
                if not isinstance(mid, str) or not re.match(r"^[a-zA-Z0-9_-]+$", mid):
                    return jsonify(self._error(f"memory_id 格式无效: {mid}"))

            deleted_count = 0
            for mid in memory_ids:
                if await self.memory_service.delete_memory(mid):
                    deleted_count += 1

            return jsonify({"deleted_count": deleted_count})
        except Exception as e:
            logger.error(f"批量删除记忆失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def delete_single_memory(self, memory_id: str) -> Any:
        try:
            if not memory_id:
                return jsonify(self._error("缺少 memory_id 参数"))
            mid = str(memory_id).strip()
            if not mid:
                return jsonify(self._error("memory_id 不能为空"))
            if not re.match(r"^[a-zA-Z0-9_-]+$", mid):
                return jsonify(self._error("memory_id 格式无效"))
            success = await self.memory_service.delete_memory(mid)
            if not success:
                return jsonify(self._error("删除失败"))
            return jsonify({"deleted": True})
        except Exception as e:
            logger.error(f"删除记忆失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def delete_session_memories(self, session_id: str) -> Any:
        try:
            if not session_id:
                return jsonify(self._error("缺少 session_id 参数"))
            count = await self.memory_service.delete_session_memories(str(session_id).strip())
            return jsonify({"deleted_count": count})
        except Exception as e:
            logger.error(f"删除会话记忆失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def export_memories(self) -> Any:
        try:
            fmt = request.args.get("format", "json")
            session_id = request.args.get("session_id") or None
            start_date = request.args.get("start_date") or None
            end_date = request.args.get("end_date") or None

            start_datetime = datetime.fromisoformat(start_date) if start_date else None
            end_datetime = datetime.fromisoformat(end_date) if end_date else None

            content = await self.memory_service.export_memories(
                format=fmt, session_id=session_id,
                start_date=start_datetime, end_date=end_datetime,
            )
            if content is None:
                return jsonify(self._error("导出失败"))

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"memories_export_{timestamp}.{fmt}"
            media_type = "application/json" if fmt == "json" else "text/csv"

            resp = Response(content, content_type=media_type)
            resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            return resp
        except Exception as e:
            logger.error(f"导出记忆失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def vector_search_memories(self) -> Any:
        try:
            body = await request.get_json(silent=True) or {}
            query = body.get("query", "")
            try:
                limit = int(body.get("limit", 50))
                limit = max(1, min(limit, 100))
            except (ValueError, TypeError):
                limit = 50
            if not query:
                return jsonify(self._error("查询内容不能为空"))
            results = await self.memory_service.vector_search(query, limit)
            return jsonify({"records": results, "total_count": len(results)})
        except Exception as e:
            logger.error(f"向量检索失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    # ==================== 配置 API ====================

    _SENSITIVE_KEYS = {"authentication"}

    async def get_config(self) -> Any:
        try:
            config = self.plugin.config.copy()
            # 排除敏感配置项，避免密码等泄露到前端
            for key in self._SENSITIVE_KEYS:
                config.pop(key, None)
            return jsonify(config)
        except Exception as e:
            logger.error(f"获取配置失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))

    async def update_config(self) -> Any:
        try:
            data = await request.get_json(silent=True) or {}
            for key, value in data.items():
                # 禁止通过全量保存覆盖敏感配置项
                if key in self._SENSITIVE_KEYS:
                    continue
                self.plugin.config[key] = value
            self.plugin.save_config()
            return jsonify({"saved": True})
        except Exception as e:
            logger.error(f"更新配置失败: {e}", exc_info=True)
            return jsonify(self._error(str(e)))
