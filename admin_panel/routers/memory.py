"""
记忆管理相关路由
提供记忆查询、统计、编辑、删除、导出等 API
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from astrbot.core.log import LogManager

from ..services.memory_service import MemoryService

logger = LogManager.GetLogger(log_name="MemoryRoutes")


def setup_memory_routes(app, plugin_instance):
    """
    设置记忆管理相关路由

    Args:
        app: Web 应用实例
        plugin_instance: Mnemosyne 插件实例
    """
    memory_service = MemoryService(plugin_instance)
    router = APIRouter()

    # API: 搜索记忆
    @router.post("/api/memories/search")
    async def search_memories(
        request: Request,
        session_id: str | None = Query(None),
        keyword: str | None = Query(None),
        start_date: str | None = Query(None),
        end_date: str | None = Query(None),
        persona_id: str | None = Query(None),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0),
        sort_by: str = Query("create_time"),
        sort_order: str = Query("desc"),
    ):
        try:
            start_datetime = datetime.fromisoformat(start_date) if start_date else None
            end_datetime = datetime.fromisoformat(end_date) if end_date else None

            from ..models.memory import MemorySearchRequest

            search_req = MemorySearchRequest(
                session_id=session_id,
                keyword=keyword,
                start_date=start_datetime,
                end_date=end_datetime,
                persona_id=persona_id,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order,
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

    # API: 获取记忆统计
    @router.get("/api/memories/statistics")
    async def get_memory_statistics(request: Request):
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

    # API: 获取会话列表
    @router.get("/api/memories/sessions")
    async def get_session_list(
        request: Request, limit: int = Query(100, ge=1, le=1000)
    ):
        try:
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

    # API: 删除单条记忆
    @router.delete("/api/memories/{memory_id}")
    async def delete_memory(memory_id: str, request: Request):
        try:
            # M15 修复: 增强 memory_id 输入验证
            if not memory_id:
                raise HTTPException(status_code=400, detail="缺少 memory_id 参数")

            # 验证 memory_id 类型
            if not isinstance(memory_id, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"memory_id 参数类型无效，必须是字符串，当前类型: {type(memory_id).__name__}",
                )

            # 转换为字符串并验证
            memory_id_str = str(memory_id).strip()
            if not memory_id_str:
                raise HTTPException(status_code=400, detail="memory_id 不能为空")

            # 验证格式（只允许数字、字母、下划线、连字符）
            import re

            if not re.match(r"^[a-zA-Z0-9_-]+$", memory_id_str):
                raise HTTPException(
                    status_code=400,
                    detail="memory_id 格式无效，只允许字母、数字、下划线和连字符",
                )

            # 使用验证后的 memory_id
            memory_id = memory_id_str

            success = await memory_service.delete_memory(memory_id)

            if success:
                return {"success": True, "message": "记忆已删除"}
            else:
                raise HTTPException(status_code=404, detail="删除失败")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"删除记忆失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # API: 删除会话的所有记忆
    @router.delete("/api/memories/session/{session_id}")
    async def delete_session_memories(session_id: str, request: Request):
        try:
            if not session_id:
                raise HTTPException(status_code=400, detail="缺少 session_id 参数")

            count = await memory_service.delete_session_memories(session_id)

            return {
                "success": True,
                "message": f"已删除 {count} 条记忆",
                "deleted_count": count,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"删除会话记忆失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # API: 导出记忆
    @router.post("/api/memories/export")
    async def export_memories(
        request: Request,
        format: str = Query("json"),
        session_id: str | None = Query(None),
        start_date: str | None = Query(None),
        end_date: str | None = Query(None),
    ):
        try:
            start_datetime = datetime.fromisoformat(start_date) if start_date else None
            end_datetime = datetime.fromisoformat(end_date) if end_date else None

            content = await memory_service.export_memories(
                format=format,
                session_id=session_id,
                start_date=start_datetime,
                end_date=end_datetime,
            )

            if content is None:
                raise HTTPException(status_code=500, detail="导出失败")

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"memories_export_{timestamp}.{format}"

            return {
                "success": True,
                "data": content,
                "format": format,
                "filename": filename,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"导出记忆失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # 将路由器包含到主应用中
    app.include_router(router)

    logger.info("记忆管理路由已注册")
