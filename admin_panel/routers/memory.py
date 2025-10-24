# -*- coding: utf-8 -*-
"""
记忆管理相关路由
提供记忆查询、统计、编辑、删除、导出等 API
"""

from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from astrbot.core.log import LogManager
from astrbot.api.star import StarTools
from ..services.memory_service import MemoryService
from ..models.memory import MemorySearchRequest
from ..middleware.auth import create_auth_middleware

logger = LogManager.GetLogger(log_name="MemoryRoutes")


def setup_memory_routes(app, plugin_instance):
    """
    设置记忆管理相关路由
    
    Args:
        app: Web 应用实例
        plugin_instance: Mnemosyne 插件实例
    """
    memory_service = MemoryService(plugin_instance)
    
    # 创建认证中间件，使用标准的插件数据目录
    api_key = plugin_instance.config.get("admin_panel", {}).get("api_key")
    data_dir = Path(StarTools.get_data_dir()) / "admin_panel"
    auth = create_auth_middleware(api_key, data_dir)
    
    # API: 搜索记忆（需要认证）
    @auth.require_auth
    async def search_memories(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/memories/search
        搜索记忆
        
        Request Body:
            {
                "session_id": "optional_session_id",
                "keyword": "搜索关键词",
                "start_date": "2025-10-01T00:00:00",
                "end_date": "2025-10-24T23:59:59",
                "persona_id": "optional_persona_id",
                "limit": 10,
                "offset": 0,
                "sort_by": "create_time",
                "sort_order": "desc"
            }
        
        Returns:
            {
                "success": true,
                "data": {
                    "records": [...],
                    "total_count": 100,
                    "page": 1,
                    "page_size": 10,
                    "has_more": true
                }
            }
        """
        try:
            # 解析请求参数
            search_req = MemorySearchRequest(
                session_id=request.get('session_id'),
                keyword=request.get('keyword'),
                start_date=datetime.fromisoformat(request['start_date']) if request.get('start_date') else None,
                end_date=datetime.fromisoformat(request['end_date']) if request.get('end_date') else None,
                persona_id=request.get('persona_id'),
                limit=request.get('limit', 10),
                offset=request.get('offset', 0),
                sort_by=request.get('sort_by', 'create_time'),
                sort_order=request.get('sort_order', 'desc')
            )
            
            response = await memory_service.search_memories(search_req)
            
            return {
                "success": True,
                "data": response.to_dict()
            }
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 获取记忆统计（需要认证）
    @auth.require_auth
    async def get_memory_statistics(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        GET /api/memories/statistics
        获取记忆统计信息
        
        Returns:
            {
                "success": true,
                "data": {
                    "total_memories": 1000,
                    "total_sessions": 50,
                    "memories_by_session": {...},
                    "memories_by_date": {...},
                    "most_active_sessions": [...],
                    "recent_memories_count": 100,
                    "average_memory_length": 250.5
                }
            }
        """
        try:
            stats = await memory_service.get_memory_statistics()
            
            return {
                "success": True,
                "data": stats.to_dict()
            }
        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 获取会话列表（需要认证）
    @auth.require_auth
    async def get_session_list(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        GET /api/memories/sessions
        获取会话列表
        
        Query Parameters:
            - limit: int, 返回数量限制（默认100）
        
        Returns:
            {
                "success": true,
                "data": [
                    {
                        "session_id": "session_123",
                        "memory_count": 50,
                        "last_memory_time": "2025-10-24T11:20:00",
                        "first_memory_time": "2025-10-01T10:00:00"
                    },
                    ...
                ]
            }
        """
        try:
            limit = request.get('limit', 100)
            sessions = await memory_service.get_session_list(limit=limit)
            
            return {
                "success": True,
                "data": sessions
            }
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 删除单条记忆（需要认证）
    @auth.require_auth
    async def delete_memory(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        DELETE /api/memories/{memory_id}
        删除单条记忆
        
        Path Parameters:
            - memory_id: str, 记忆ID
        
        Returns:
            {
                "success": true,
                "message": "记忆已删除"
            }
        """
        try:
            memory_id = request.get('memory_id')
            
            # M15 修复: 增强 memory_id 输入验证
            if not memory_id:
                return {
                    "success": False,
                    "error": "缺少 memory_id 参数"
                }
            
            # 验证 memory_id 类型
            if not isinstance(memory_id, (str, int)):
                return {
                    "success": False,
                    "error": f"memory_id 参数类型无效，必须是字符串或整数，当前类型: {type(memory_id).__name__}"
                }
            
            # 转换为字符串并验证
            memory_id_str = str(memory_id).strip()
            if not memory_id_str:
                return {
                    "success": False,
                    "error": "memory_id 不能为空"
                }
            
            # 验证格式（只允许数字、字母、下划线、连字符）
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', memory_id_str):
                return {
                    "success": False,
                    "error": "memory_id 格式无效，只允许字母、数字、下划线和连字符"
                }
            
            # 使用验证后的 memory_id
            memory_id = memory_id_str
            
            success = await memory_service.delete_memory(memory_id)
            
            if success:
                return {
                    "success": True,
                    "message": "记忆已删除"
                }
            else:
                return {
                    "success": False,
                    "error": "删除失败"
                }
        except Exception as e:
            logger.error(f"删除记忆失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 删除会话的所有记忆（需要认证）
    @auth.require_auth
    async def delete_session_memories(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        DELETE /api/memories/session/{session_id}
        删除指定会话的所有记忆
        
        Path Parameters:
            - session_id: str, 会话ID
        
        Returns:
            {
                "success": true,
                "message": "已删除 50 条记忆",
                "deleted_count": 50
            }
        """
        try:
            session_id = request.get('session_id')
            if not session_id:
                return {
                    "success": False,
                    "error": "缺少 session_id 参数"
                }
            
            count = await memory_service.delete_session_memories(session_id)
            
            return {
                "success": True,
                "message": f"已删除 {count} 条记忆",
                "deleted_count": count
            }
        except Exception as e:
            logger.error(f"删除会话记忆失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # API: 导出记忆（需要认证）
    @auth.require_auth
    async def export_memories(request: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/memories/export
        导出记忆数据
        
        Request Body:
            {
                "format": "json",  # json 或 csv
                "session_id": "optional_session_id",
                "start_date": "2025-10-01T00:00:00",
                "end_date": "2025-10-24T23:59:59"
            }
        
        Returns:
            {
                "success": true,
                "data": "导出的内容",
                "format": "json",
                "filename": "memories_export_20251024.json"
            }
        """
        try:
            format = request.get('format', 'json')
            session_id = request.get('session_id')
            start_date = datetime.fromisoformat(request['start_date']) if request.get('start_date') else None
            end_date = datetime.fromisoformat(request['end_date']) if request.get('end_date') else None
            
            content = await memory_service.export_memories(
                format=format,
                session_id=session_id,
                start_date=start_date,
                end_date=end_date
            )
            
            if content is None:
                return {
                    "success": False,
                    "error": "导出失败"
                }
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"memories_export_{timestamp}.{format}"
            
            return {
                "success": True,
                "data": content,
                "format": format,
                "filename": filename
            }
        except Exception as e:
            logger.error(f"导出记忆失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    # 注册路由
    routes = {
        '/api/memories/search': search_memories,
        '/api/memories/statistics': get_memory_statistics,
        '/api/memories/sessions': get_session_list,
        '/api/memories/delete': delete_memory,
        '/api/memories/session/delete': delete_session_memories,
        '/api/memories/export': export_memories,
    }
    
    logger.info(f"记忆管理路由已注册: {list(routes.keys())}")
    
    return routes