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

            # 优化：query 方法内部会自动处理集合加载，无需手动加载
            # 构建查询表达式
            expr_parts = []

            if request.session_id:
                expr_parts.append(f'session_id == "{request.session_id}"')

            # 注意：persona_id 字段可能不存在，需要先检查
            if request.persona_id:
                # 先检查集合是否有 persona_id 字段
                collection = self.plugin.milvus_manager.get_collection(collection_name)
                if collection:
                    schema_fields = [f.name for f in collection.schema.fields]
                    if (
                        "persona_id" in schema_fields
                        or "personality_id" in schema_fields
                    ):
                        # 使用正确的字段名
                        field_name = (
                            "personality_id"
                            if "personality_id" in schema_fields
                            else "persona_id"
                        )
                        expr_parts.append(f'{field_name} == "{request.persona_id}"')
                    else:
                        self.logger.warning(
                            "集合中不存在 persona_id 或 personality_id 字段，跳过人格过滤"
                        )

            if request.start_date:
                start_timestamp = request.start_date.timestamp()
                expr_parts.append(f"create_time >= {start_timestamp}")

            if request.end_date:
                end_timestamp = request.end_date.timestamp()
                expr_parts.append(f"create_time <= {end_timestamp}")

            expr = " && ".join(expr_parts) if expr_parts else ""

            # 动态确定 output_fields
            collection = self.plugin.milvus_manager.get_collection(collection_name)
            if not collection:
                self.logger.error(f"无法获取集合 {collection_name}")
                return MemorySearchResponse(
                    records=[],
                    total_count=0,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=False,
                )

            # 获取实际存在的字段
            schema_fields = [f.name for f in collection.schema.fields]
            output_fields = ["memory_id", "session_id", "content", "create_time"]
            # 添加可选字段
            if "personality_id" in schema_fields:
                output_fields.append("personality_id")
            elif "persona_id" in schema_fields:
                output_fields.append("persona_id")

            try:
                # 执行查询 - expression 是必需的第一个参数
                # 如果没有过滤条件，使用一个总是为真的表达式
                query_expr = expr if expr else "memory_id >= 0"
                results = self.plugin.milvus_manager.query(
                    collection_name=collection_name,
                    expression=query_expr,
                    output_fields=output_fields,
                    limit=request.limit,
                    offset=request.offset,
                )

                # 检查查询结果
                if results is None:
                    self.logger.error("查询返回 None")
                    return MemorySearchResponse(
                        records=[],
                        total_count=0,
                        page=request.offset // request.limit + 1,
                        page_size=request.limit,
                        has_more=False,
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

                        # 使用正确的字段名
                        persona_id_value = result.get("personality_id") or result.get(
                            "persona_id"
                        )

                        record = MemoryRecord(
                            memory_id=str(result.get("memory_id", "")),
                            session_id=result.get("session_id", ""),
                            content=result.get("content", ""),
                            create_time=create_time,
                            persona_id=persona_id_value,
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

            # 获取总记忆数（无需手动加载，query会自动处理）
            collection = self.plugin.milvus_manager.get_collection(collection_name)
            stats.total_memories = collection.num_entities

            # 查询所有记忆（限制数量以避免性能问题）
            max_query = min(stats.total_memories, 10000)
            if max_query > 0:
                results = self.plugin.milvus_manager.query(
                    collection_name=collection_name,
                    expression="memory_id >= 0",  # 查询所有记录
                    output_fields=["session_id", "content", "create_time"],
                    limit=max_query,
                )

                # 检查查询结果
                if not results:
                    self.logger.warning("统计查询返回空结果")
                    return stats

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

            # 删除记忆 - memory_id 是 Int64 类型，不需要引号
            try:
                # 尝试将 memory_id 转换为整数
                memory_id_int = int(memory_id)
                expr = f"memory_id == {memory_id_int}"
            except ValueError:
                # 如果转换失败，使用字符串格式（向后兼容）
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

            # 先查询记忆数量 - session_id 是字符串类型，需要引号
            results = self.plugin.milvus_manager.query(
                collection_name=collection_name,
                expression=f'session_id == "{session_id}"',
                output_fields=["memory_id"],
                limit=10000,
            )
            count = len(results) if results else 0

            # 删除记忆 - session_id 是字符串类型，需要引号
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

            # 查询所有记忆（无需手动加载，query会自动处理）
            results = self.plugin.milvus_manager.query(
                collection_name=collection_name,
                expression="memory_id >= 0",  # 查询所有记录
                output_fields=["session_id", "create_time"],
                limit=10000,
            )

            # 检查查询结果
            if not results:
                self.logger.warning("会话列表查询返回空结果")
                return []

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

    async def vector_search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        向量检索记忆

        Args:
            query: 查询文本
            limit: 返回数量限制

        Returns:
            List[Dict]: 记忆列表，按相似度排序
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

            # 使用embedding模型生成查询向量
            if (
                not hasattr(self.plugin, "embedding_model")
                or not self.plugin.embedding_model
            ):
                self.logger.warning("Embedding模型未初始化，无法进行向量检索")
                return []

            # 生成查询向量
            query_vector = self.plugin.embedding_model.encode(query)

            # 获取集合
            collection = self.plugin.milvus_manager.get_collection(collection_name)
            if not collection:
                self.logger.error(f"无法获取集合 {collection_name}")
                return []

            # 获取实际存在的字段
            schema_fields = [f.name for f in collection.schema.fields]
            output_fields = ["memory_id", "session_id", "content", "create_time"]

            # 添加可选字段
            if "personality_id" in schema_fields:
                output_fields.append("personality_id")
            elif "persona_id" in schema_fields:
                output_fields.append("persona_id")

            # 执行向量搜索
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}

            results = self.plugin.milvus_manager.search(
                collection_name=collection_name,
                query_vectors=[query_vector],
                anns_field="embedding",
                limit=limit,
                output_fields=output_fields,
                search_params=search_params,
            )

            # 转换结果
            memories = []
            if results and len(results) > 0:
                for hit in results[0]:
                    try:
                        entity = hit.entity

                        # 获取时间
                        create_time = entity.get("create_time")
                        if isinstance(create_time, (int, float)):
                            create_time = datetime.fromtimestamp(create_time)
                        elif isinstance(create_time, str):
                            create_time = datetime.fromisoformat(create_time)
                        else:
                            create_time = datetime.now()

                        # 获取人格ID
                        persona_id_value = entity.get("personality_id") or entity.get(
                            "persona_id"
                        )

                        memory = {
                            "memory_id": str(entity.get("memory_id", "")),
                            "session_id": entity.get("session_id", ""),
                            "content": entity.get("content", ""),
                            "create_time": create_time.isoformat(),
                            "persona_id": persona_id_value,
                            "similarity_score": 1.0
                            / (1.0 + hit.distance),  # 转换距离为相似度
                        }
                        memories.append(memory)
                    except Exception as e:
                        self.logger.error(f"转换搜索结果失败: {e}")
                        continue

            return memories

        except Exception as e:
            self.logger.error(f"向量检索失败: {e}", exc_info=True)
            return []
