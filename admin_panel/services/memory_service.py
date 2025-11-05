"""
记忆管理服务 - 提供记忆查询、统计、导出等功能
"""

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from astrbot.core.log import LogManager

from ..models.memory import (
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStatistics,
)


class MemoryService:
    """记忆管理服务"""

    def __init__(self, plugin_instance):
        """
        初始化记忆服务

        Args:
            plugin_instance: Mnemosyne 插件实例
        """
        self.plugin = plugin_instance
        self.logger = LogManager.GetLogger(log_name="MemoryService")

    async def search_memories(
        self, request: MemorySearchRequest
    ) -> MemorySearchResponse:
        """
        搜索记忆

        Args:
            request: 搜索请求

        Returns:
            MemorySearchResponse: 搜索结果
        """
        try:
            if (
                not self.plugin.milvus_manager
                or not self.plugin.milvus_manager.is_connected()
            ):
                return MemorySearchResponse(
                    records=[],
                    total_count=0,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=False,
                )

            collection_name = self.plugin.collection_name
            if not self.plugin.milvus_manager.has_collection(collection_name):
                return MemorySearchResponse(
                    records=[],
                    total_count=0,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=False,
                )

            # 构建查询表达式
            expr_parts = []

            if request.session_id:
                expr_parts.append(f'session_id == "{request.session_id}"')

            if request.persona_id:
                expr_parts.append(f'persona_id == "{request.persona_id}"')

            if request.start_date:
                start_timestamp = request.start_date.timestamp()
                expr_parts.append(f"create_time >= {start_timestamp}")

            if request.end_date:
                end_timestamp = request.end_date.timestamp()
                expr_parts.append(f"create_time <= {end_timestamp}")

            expr = " && ".join(expr_parts) if expr_parts else ""

            # 查询记忆
            output_fields = [
                "memory_id",
                "session_id",
                "content",
                "create_time",
                "persona_id",
            ]

            try:
                # 获取总数
                collection = self.plugin.milvus_manager.get_collection(collection_name)

                # 执行查询
                results = self.plugin.milvus_manager.query(
                    collection_name=collection_name,
                    expr=expr if expr else None,
                    output_fields=output_fields,
                    limit=request.limit,
                    offset=request.offset,
                )

                # 转换为 MemoryRecord
                records = []
                for result in results:
                    try:
                        create_time = result.get("create_time")
                        if isinstance(create_time, (int, float)):
                            create_time = datetime.fromtimestamp(create_time)
                        elif isinstance(create_time, str):
                            create_time = datetime.fromisoformat(create_time)
                        else:
                            create_time = datetime.now()

                        record = MemoryRecord(
                            memory_id=str(result.get("memory_id", "")),
                            session_id=result.get("session_id", ""),
                            content=result.get("content", ""),
                            create_time=create_time,
                            persona_id=result.get("persona_id"),
                        )
                        records.append(record)
                    except Exception as e:
                        self.logger.error(f"转换记忆记录失败: {e}")
                        continue

                # 如果有关键词过滤，在内存中进行过滤
                if request.keyword:
                    keyword_lower = request.keyword.lower()
                    records = [r for r in records if keyword_lower in r.content.lower()]

                # 排序
                if request.sort_by == "create_time":
                    records.sort(
                        key=lambda x: x.create_time,
                        reverse=(request.sort_order == "desc"),
                    )

                # 获取总数（近似值）
                total_count = (
                    collection.num_entities
                    if not expr
                    else len(records) + request.offset
                )
                has_more = len(records) == request.limit

                return MemorySearchResponse(
                    records=records,
                    total_count=total_count,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=has_more,
                )

            except Exception as e:
                self.logger.error(f"查询 Milvus 失败: {e}", exc_info=True)
                return MemorySearchResponse(
                    records=[],
                    total_count=0,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=False,
                )

        except Exception as e:
            self.logger.error(f"搜索记忆失败: {e}", exc_info=True)
            return MemorySearchResponse(
                records=[],
                total_count=0,
                page=request.offset // request.limit + 1,
                page_size=request.limit,
                has_more=False,
            )

    async def get_memory_statistics(self) -> MemoryStatistics:
        """
        获取记忆统计信息

        Returns:
            MemoryStatistics: 统计信息
        """
        stats = MemoryStatistics()

        try:
            if (
                not self.plugin.milvus_manager
                or not self.plugin.milvus_manager.is_connected()
            ):
                return stats

            collection_name = self.plugin.collection_name
            if not self.plugin.milvus_manager.has_collection(collection_name):
                return stats

            # 获取总记忆数
            collection = self.plugin.milvus_manager.get_collection(collection_name)
            stats.total_memories = collection.num_entities

            # 查询所有记忆（限制数量以避免性能问题）
            max_query = min(stats.total_memories, 10000)
            if max_query > 0:
                results = self.plugin.milvus_manager.query(
                    collection_name=collection_name,
                    expr=None,
                    output_fields=["session_id", "content", "create_time"],
                    limit=max_query,
                )

                # 统计各会话的记忆数
                session_counts = defaultdict(int)
                date_counts = defaultdict(int)
                total_length = 0
                recent_count = 0
                now = datetime.now()
                recent_threshold = now - timedelta(days=7)

                for result in results:
                    session_id = result.get("session_id", "unknown")
                    session_counts[session_id] += 1

                    # 内容长度统计
                    content = result.get("content", "")
                    total_length += len(content)

                    # 日期统计
                    create_time = result.get("create_time")
                    if isinstance(create_time, (int, float)):
                        create_time = datetime.fromtimestamp(create_time)
                    elif isinstance(create_time, str):
                        try:
                            create_time = datetime.fromisoformat(create_time)
                        except (ValueError, TypeError):
                            create_time = None

                    if create_time:
                        date_key = create_time.strftime("%Y-%m-%d")
                        date_counts[date_key] += 1

                        # 最近记忆统计
                        if create_time >= recent_threshold:
                            recent_count += 1

                stats.total_sessions = len(session_counts)
                stats.memories_by_session = dict(session_counts)
                stats.memories_by_date = dict(date_counts)

                # 最活跃的会话（Top 10）
                stats.most_active_sessions = sorted(
                    session_counts.items(), key=lambda x: x[1], reverse=True
                )[:10]

                stats.recent_memories_count = recent_count
                stats.average_memory_length = (
                    total_length / len(results) if results else 0.0
                )

        except Exception as e:
            self.logger.error(f"获取记忆统计失败: {e}", exc_info=True)

        return stats

    async def delete_memory(self, memory_id: str) -> bool:
        """
        删除单条记忆

        Args:
            memory_id: 记忆ID

        Returns:
            bool: 是否成功
        """
        try:
            if (
                not self.plugin.milvus_manager
                or not self.plugin.milvus_manager.is_connected()
            ):
                return False

            collection_name = self.plugin.collection_name
            if not self.plugin.milvus_manager.has_collection(collection_name):
                return False

            # 删除记忆
            expr = f'memory_id == "{memory_id}"'
            self.plugin.milvus_manager.delete(collection_name, expr)

            self.logger.info(f"已删除记忆: {memory_id}")
            return True

        except Exception as e:
            self.logger.error(f"删除记忆失败: {e}", exc_info=True)
            return False

    async def delete_session_memories(self, session_id: str) -> int:
        """
        删除指定会话的所有记忆

        Args:
            session_id: 会话ID

        Returns:
            int: 删除的记忆数量
        """
        try:
            if (
                not self.plugin.milvus_manager
                or not self.plugin.milvus_manager.is_connected()
            ):
                return 0

            collection_name = self.plugin.collection_name
            if not self.plugin.milvus_manager.has_collection(collection_name):
                return 0

            # 先查询记忆数量
            results = self.plugin.milvus_manager.query(
                collection_name=collection_name,
                expr=f'session_id == "{session_id}"',
                output_fields=["memory_id"],
                limit=10000,
            )
            count = len(results)

            # 删除记忆
            if count > 0:
                expr = f'session_id == "{session_id}"'
                self.plugin.milvus_manager.delete(collection_name, expr)

                self.logger.info(f"已删除会话 {session_id} 的 {count} 条记忆")

            return count

        except Exception as e:
            self.logger.error(f"删除会话记忆失败: {e}", exc_info=True)
            return 0

    async def export_memories(
        self,
        format: str = "json",
        session_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> str | None:
        """
        导出记忆

        Args:
            format: 导出格式 (json/csv)
            session_id: 会话ID（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            str: 导出的内容
        """
        try:
            # 构建搜索请求
            request = MemorySearchRequest(
                session_id=session_id,
                start_date=start_date,
                end_date=end_date,
                limit=10000,  # 最多导出10000条
                offset=0,
            )

            # 搜索记忆
            response = await self.search_memories(request)

            if format == "json":
                # JSON 格式
                data = {
                    "export_time": datetime.now().isoformat(),
                    "total_count": len(response.records),
                    "filters": {
                        "session_id": session_id,
                        "start_date": start_date.isoformat() if start_date else None,
                        "end_date": end_date.isoformat() if end_date else None,
                    },
                    "memories": [record.to_dict() for record in response.records],
                }
                return json.dumps(data, ensure_ascii=False, indent=2)

            elif format == "csv":
                # CSV 格式
                output = io.StringIO()
                writer = csv.writer(output)

                # 写入标题行
                writer.writerow(["记忆ID", "会话ID", "内容", "创建时间", "人格ID"])

                # 写入数据
                for record in response.records:
                    writer.writerow(
                        [
                            record.memory_id,
                            record.session_id,
                            record.content,
                            record.create_time.isoformat(),
                            record.persona_id or "",
                        ]
                    )

                return output.getvalue()

            else:
                self.logger.error(f"不支持的导出格式: {format}")
                return None

        except Exception as e:
            self.logger.error(f"导出记忆失败: {e}", exc_info=True)
            return None

    async def get_session_list(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        获取会话列表

        Args:
            limit: 返回数量限制

        Returns:
            List[Dict]: 会话列表
        """
        try:
            if (
                not self.plugin.milvus_manager
                or not self.plugin.milvus_manager.is_connected()
            ):
                return []

            collection_name = self.plugin.collection_name
            if not self.plugin.milvus_manager.has_collection(collection_name):
                return []

            # 查询所有记忆
            results = self.plugin.milvus_manager.query(
                collection_name=collection_name,
                expr=None,
                output_fields=["session_id", "create_time"],
                limit=10000,
            )

            # 统计每个会话
            session_data: dict[str, dict[str, Any]] = defaultdict(
                lambda: {
                    "session_id": "",
                    "memory_count": 0,
                    "last_memory_time": None,
                    "first_memory_time": None,
                }
            )

            for result in results:
                session_id = result.get("session_id", "unknown")
                create_time_raw = result.get("create_time")

                create_time: datetime
                if isinstance(create_time_raw, (int, float)):
                    create_time = datetime.fromtimestamp(create_time_raw)
                elif isinstance(create_time_raw, str):
                    try:
                        create_time = datetime.fromisoformat(create_time_raw)
                    except (ValueError, TypeError):
                        create_time = datetime.now()
                else:
                    create_time = datetime.now()

                session_info = session_data[session_id]
                session_info["session_id"] = session_id
                session_info["memory_count"] = session_info["memory_count"] + 1

                last_time = session_info["last_memory_time"]
                if last_time is None or (
                    isinstance(last_time, datetime) and create_time > last_time
                ):
                    session_info["last_memory_time"] = create_time

                first_time = session_info["first_memory_time"]
                if first_time is None or (
                    isinstance(first_time, datetime) and create_time < first_time
                ):
                    session_info["first_memory_time"] = create_time

            # 转换为列表并排序
            sessions = list(session_data.values())
            sessions.sort(
                key=lambda x: x["last_memory_time"]
                if x["last_memory_time"]
                else datetime.min,
                reverse=True,
            )

            # 格式化时间
            for session in sessions[:limit]:
                last_time = session.get("last_memory_time")
                if last_time and isinstance(last_time, datetime):
                    session["last_memory_time"] = last_time.isoformat()

                first_time = session.get("first_memory_time")
                if first_time and isinstance(first_time, datetime):
                    session["first_memory_time"] = first_time.isoformat()

            return sessions[:limit]

        except Exception as e:
            self.logger.error(f"获取会话列表失败: {e}", exc_info=True)
            return []
