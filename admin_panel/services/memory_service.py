"""
记忆管理服务 - 提供记忆查询、统计、导出等功能
"""

import asyncio
import csv
import heapq
import io
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from astrbot.api import logger

from ..models.memory import (
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStatistics,
)

# 兼容两种加载场景：
# - 运行时：admin_panel 作为插件子包，`...core` 可达插件根的 core 模块。
# - 测试时：admin_panel 作为顶层包，`...core` 会超出顶层包，回退到绝对导入
#   （测试已将插件根加入 sys.path，core 作为顶层包可用）。
try:
    from ...core.provider_utils import request_embedding
    from ...core.security_utils import safe_build_milvus_expression
except ImportError:
    from core.provider_utils import request_embedding
    from core.security_utils import safe_build_milvus_expression


MEMORY_SERVICE_CACHE_TTL_SECONDS = 10.0
BATCH_DELETE_CHUNK_SIZE = 200
ADMIN_QUERY_PAGE_SIZE = 2000


class MemoryService:
    """记忆管理服务"""

    def __init__(self, plugin_instance):
        """
        初始化记忆服务

        Args:
            plugin_instance: Mnemosyne 插件实例
        """
        self.plugin = plugin_instance
        self.logger = logger
        self._stats_cache: MemoryStatistics | None = None
        self._stats_cache_at = 0.0
        self._sessions_cache: list[dict[str, Any]] | None = None
        self._sessions_cache_at = 0.0

    def _invalidate_caches(self) -> None:
        self._stats_cache = None
        self._sessions_cache = None

    def _get_vector_db(self):
        return getattr(self.plugin, "vector_db", None)

    def _all_records_expr(self) -> str | None:
        return None

    def _vector_db_type(self) -> str:
        return str(
            getattr(self.plugin, "config", {}).get("vector_db_type", "chroma")
        ).lower()

    @staticmethod
    def _native_id_expr(memory_id: str) -> str:
        normalized = str(memory_id).strip().strip('"`')
        return f'id == "{normalized}"'

    def _delete_identity_expr(self, memory_id: str) -> str:
        if self._vector_db_type() == "milvus":
            try:
                return f"memory_id == {int(memory_id)}"
            except ValueError:
                return f'memory_id == "{memory_id}"'
        return self._native_id_expr(memory_id)

    @staticmethod
    def _record_id(result: dict[str, Any]) -> str:
        native_id = result.get("id")
        additional = result.get("_additional")
        if not native_id and isinstance(additional, dict):
            native_id = additional.get("id")
        return str(result.get("memory_id") or native_id or "")

    async def _count_records(
        self,
        vector_db,
        collection_name: str,
        filters: str | None,
    ) -> int | None:
        return await asyncio.to_thread(
            vector_db.count,
            collection_name,
            filters,
        )

    async def _iter_query_batches(
        self,
        vector_db,
        collection_name: str,
        filters: str | None,
        output_fields: list[str],
        expected_total: int | None = None,
    ):
        offset = 0
        while expected_total is None or offset < expected_total:
            page_size = ADMIN_QUERY_PAGE_SIZE
            if expected_total is not None:
                page_size = min(page_size, expected_total - offset)
            batch = await asyncio.to_thread(
                vector_db.query,
                collection_name=collection_name,
                filters=filters,
                output_fields=output_fields,
                limit=page_size,
                offset=offset,
            )
            if not batch:
                break
            yield batch
            offset += len(batch)
            if len(batch) < page_size:
                break

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
            vector_db = self._get_vector_db()
            if not vector_db or not vector_db.is_connected():
                return MemorySearchResponse(
                    records=[],
                    total_count=0,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=False,
                )

            collection_name = self.plugin.collection_name
            if not await asyncio.to_thread(
                vector_db.has_collection, collection_name
            ):
                return MemorySearchResponse(
                    records=[],
                    total_count=0,
                    page=request.offset // request.limit + 1,
                    page_size=request.limit,
                    has_more=False,
                )

            # 优化：query 方法内部会自动处理集合加载，无需手动加载
            # 构建查询表达式（仅标量过滤；keyword 需要在内存中匹配）
            expr_parts = []

            if request.session_id:
                expr_parts.append(
                    safe_build_milvus_expression("session_id", request.session_id, "==")
                )

            # 注意：persona_id 字段可能不存在，需要先检查
            if request.persona_id:
                expr_parts.append(
                    safe_build_milvus_expression(
                        "personality_id", request.persona_id, "=="
                    )
                )

            if request.start_date:
                start_timestamp = request.start_date.timestamp()
                expr_parts.append(f"create_time >= {start_timestamp}")

            if request.end_date:
                end_timestamp = request.end_date.timestamp()
                expr_parts.append(f"create_time <= {end_timestamp}")

            expr = " and ".join(expr_parts) if expr_parts else ""

            output_fields = ["memory_id", "session_id", "content", "create_time"]
            output_fields.append("personality_id")

            try:
                query_expr = expr if expr else self._all_records_expr()
                page = request.offset // request.limit + 1

                def _to_record(result: dict[str, Any]) -> MemoryRecord | None:
                    try:
                        create_time = result.get("create_time")
                        if isinstance(create_time, (int, float)):
                            create_time_dt = datetime.fromtimestamp(create_time)
                        elif isinstance(create_time, str):
                            create_time_dt = datetime.fromisoformat(create_time)
                        elif isinstance(create_time, datetime):
                            create_time_dt = create_time
                        else:
                            create_time_dt = datetime.now()

                        persona_id_value = result.get("personality_id") or result.get(
                            "persona_id"
                        )
                        memory_type = result.get("memory_type", "long_term")

                        record = MemoryRecord(
                            memory_id=self._record_id(result),
                            session_id=result.get("session_id", ""),
                            content=result.get("content", ""),
                            create_time=create_time_dt,
                            persona_id=persona_id_value,
                        )
                        record.metadata["memory_type"] = memory_type
                        return record
                    except Exception as exc:
                        self.logger.error(f"转换记忆记录失败: {exc}")
                        return None

                native_total = None
                if not request.keyword:
                    native_total = await self._count_records(
                        vector_db, collection_name, query_expr
                    )
                if native_total == 0 or (
                    native_total is not None and request.offset >= native_total
                ):
                    return MemorySearchResponse(
                        records=[],
                        total_count=native_total or 0,
                        page=page,
                        page_size=request.limit,
                        has_more=False,
                    )

                window = request.offset + request.limit
                is_desc = request.sort_order == "desc"
                keyword_lower = request.keyword.lower() if request.keyword else None
                heap: list[tuple[float, int, MemoryRecord]] = []
                unordered: list[MemoryRecord] = []
                matched_count = 0

                async for batch in self._iter_query_batches(
                    vector_db,
                    collection_name,
                    query_expr,
                    output_fields,
                    expected_total=native_total,
                ):
                    for result in batch:
                        record = _to_record(result)
                        if record is None:
                            continue
                        if keyword_lower and keyword_lower not in (
                            record.content or ""
                        ).lower():
                            continue

                        matched_count += 1
                        if request.sort_by != "create_time":
                            unordered.append(record)
                            continue

                        timestamp = record.create_time.timestamp()
                        heap_key = timestamp if is_desc else -timestamp
                        heapq.heappush(
                            heap, (heap_key, matched_count, record)
                        )
                        if len(heap) > window:
                            heapq.heappop(heap)

                total_count = (
                    native_total if native_total is not None else matched_count
                )
                if request.sort_by == "create_time":
                    ordered = [entry[2] for entry in heap]
                    ordered.sort(key=lambda item: item.create_time, reverse=is_desc)
                else:
                    ordered = unordered
                start = min(request.offset, len(ordered))
                end = min(request.offset + request.limit, len(ordered))
                page_records = ordered[start:end]
                has_more = request.offset + request.limit < total_count

                return MemorySearchResponse(
                    records=page_records,
                    total_count=total_count,
                    page=page,
                    page_size=request.limit,
                    has_more=has_more,
                )

            except Exception as e:
                self.logger.error(f"查询向量数据库失败: {e}", exc_info=True)
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
        now = time.monotonic()
        if (
            self._stats_cache is not None
            and now - self._stats_cache_at < MEMORY_SERVICE_CACHE_TTL_SECONDS
        ):
            return self._stats_cache

        stats = MemoryStatistics()

        try:
            vector_db = self._get_vector_db()
            if not vector_db or not vector_db.is_connected():
                return stats

            collection_name = self.plugin.collection_name
            if not await asyncio.to_thread(
                vector_db.has_collection, collection_name
            ):
                return stats

            native_total = await self._count_records(vector_db, collection_name, None)
            if native_total == 0:
                self._stats_cache = stats
                self._stats_cache_at = time.monotonic()
                return stats

            session_counts = defaultdict(int)
            date_counts = defaultdict(int)
            total_length = 0
            recent_count = 0
            scanned_count = 0
            recent_threshold = datetime.now() - timedelta(days=7)

            async for results in self._iter_query_batches(
                vector_db,
                collection_name,
                self._all_records_expr(),
                ["session_id", "content", "create_time"],
                expected_total=native_total,
            ):
                for result in results:
                    scanned_count += 1
                    session_id = result.get("session_id", "unknown")
                    session_counts[session_id] += 1
                    total_length += len(result.get("content", ""))

                    create_time = result.get("create_time")
                    if isinstance(create_time, (int, float)):
                        create_time = datetime.fromtimestamp(create_time)
                    elif isinstance(create_time, str):
                        try:
                            create_time = datetime.fromisoformat(create_time)
                        except (ValueError, TypeError):
                            create_time = None

                    if create_time:
                        date_counts[create_time.strftime("%Y-%m-%d")] += 1
                        if create_time >= recent_threshold:
                            recent_count += 1

            stats.total_memories = (
                native_total if native_total is not None else scanned_count
            )
            stats.total_sessions = len(session_counts)
            stats.memories_by_session = dict(session_counts)
            stats.memories_by_date = dict(date_counts)
            stats.most_active_sessions = sorted(
                session_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
            stats.recent_memories_count = recent_count
            stats.average_memory_length = (
                total_length / scanned_count if scanned_count else 0.0
            )

        except Exception as e:
            self.logger.error(f"获取记忆统计失败: {e}", exc_info=True)
            return stats

        self._stats_cache = stats
        self._stats_cache_at = time.monotonic()
        return stats

    async def batch_delete_memories(self, memory_ids: list[str]) -> int:
        """删除多条记忆，按块合并表达式并只 flush 一次。"""
        unique_ids = list(dict.fromkeys(memory_ids))
        if not unique_ids:
            return 0

        vector_db = self._get_vector_db()
        if not vector_db or not vector_db.is_connected():
            return 0

        collection_name = self.plugin.collection_name
        if not await asyncio.to_thread(
            vector_db.has_collection, collection_name
        ):
            return 0

        deleted_count = 0
        for start in range(0, len(unique_ids), BATCH_DELETE_CHUNK_SIZE):
            chunk = unique_ids[start : start + BATCH_DELETE_CHUNK_SIZE]
            expr = " or ".join(
                self._delete_identity_expr(memory_id) for memory_id in chunk
            )
            mutation_result = await asyncio.to_thread(
                vector_db.delete, collection_name, expr
            )
            result_count = getattr(mutation_result, "delete_count", None)
            deleted_count += len(chunk) if result_count is None else result_count

        await asyncio.to_thread(vector_db.flush, [collection_name])
        self._invalidate_caches()
        self.logger.info(
            f"批量删除 {len(unique_ids)} 条记忆，实际删除 {deleted_count} 条"
        )
        return deleted_count

    async def delete_memory(self, memory_id: str) -> bool:
        """
        删除单条记忆

        Args:
            memory_id: 记忆ID

        Returns:
            bool: 是否成功
        """
        try:
            vector_db = self._get_vector_db()
            if not vector_db or not vector_db.is_connected():
                return False

            collection_name = self.plugin.collection_name
            if not await asyncio.to_thread(
                vector_db.has_collection, collection_name
            ):
                return False

            expr = self._delete_identity_expr(memory_id)

            mutation_result = await asyncio.to_thread(
                vector_db.delete, collection_name, expr
            )
            await asyncio.to_thread(vector_db.flush, [collection_name])

            delete_count = getattr(mutation_result, "delete_count", None)
            self.logger.info(f"已删除记忆: {memory_id}, 删除计数: {delete_count}")
            self._invalidate_caches()
            return delete_count is None or delete_count > 0

        except Exception as e:
            self.logger.error(f"删除记忆失败: {e}", exc_info=True)
            return False

    async def update_memory(self, memory_id: str, content: str) -> dict[str, Any]:
        """更新记忆内容并重新生成 embedding。"""
        normalized_content = str(content or "").strip()
        if not normalized_content:
            raise ValueError("记忆内容不能为空")
        if len(normalized_content) > 4096:
            raise ValueError("记忆内容不能超过 4096 个字符")

        vector_db = self._get_vector_db()
        if not vector_db or not vector_db.is_connected():
            raise RuntimeError("向量数据库未连接")

        collection_name = self.plugin.collection_name
        if not await asyncio.to_thread(
            vector_db.has_collection, collection_name
        ):
            raise RuntimeError("记忆集合不存在")

        if not getattr(self.plugin, "embedding_provider", None):
            raise RuntimeError("Embedding Provider 未初始化")

        backend = self._vector_db_type()
        output_fields = ["session_id", "content", "create_time", "personality_id"]
        if backend == "milvus":
            output_fields.append("memory_id")
        try:
            original = await asyncio.to_thread(
                vector_db.get_by_id,
                collection_name=collection_name,
                record_id=memory_id,
                output_fields=output_fields,
            )
        except NotImplementedError as e:
            raise RuntimeError("当前向量数据库不支持按 ID 更新记忆") from e

        if not original:
            raise ValueError("记忆记录不存在")

        original_content = str(original.get("content", ""))
        create_time = original.get("create_time")
        if isinstance(create_time, datetime):
            create_time = create_time.timestamp()
        elif isinstance(create_time, str):
            try:
                create_time = datetime.fromisoformat(create_time).timestamp()
            except ValueError:
                create_time = datetime.now().timestamp()
        elif not isinstance(create_time, (int, float)):
            create_time = datetime.now().timestamp()

        new_embedding = await request_embedding(self.plugin, normalized_content)
        if not new_embedding:
            raise RuntimeError("无法为更新后的记忆生成 embedding")

        updated_payload = {
            "content": normalized_content,
            "embedding": new_embedding,
            "personality_id": original.get("personality_id", ""),
            "session_id": original.get("session_id", ""),
            "create_time": int(create_time),
        }

        if backend != "milvus":
            try:
                result = await asyncio.to_thread(
                    vector_db.update,
                    collection_name,
                    memory_id,
                    updated_payload,
                )
            except NotImplementedError as e:
                raise RuntimeError("当前向量数据库不支持原地更新记忆") from e
            await asyncio.to_thread(vector_db.flush, [collection_name])
            if result.insert_count != 1:
                raise RuntimeError("向量数据库未确认更新操作")
            updated_id = (
                str(result.primary_keys[0]) if result.primary_keys else memory_id
            )
            self._invalidate_caches()
            return self._updated_memory_response(memory_id, updated_id, updated_payload)

        # Milvus 集合使用 AutoID，无法原地保留主键。删除前同时生成旧向量，
        # 这样新记录插入失败时仍可恢复原内容。
        original_embedding = await request_embedding(self.plugin, original_content)
        if not original_embedding:
            raise RuntimeError("无法生成回滚所需的原记忆 embedding")

        try:
            numeric_id = int(memory_id)
            filters = f"memory_id == {numeric_id}"
        except ValueError:
            filters = f'memory_id == "{memory_id}"'

        delete_result = await asyncio.to_thread(
            vector_db.delete, collection_name, filters
        )
        await asyncio.to_thread(vector_db.flush, [collection_name])
        if delete_result.delete_count is not None and delete_result.delete_count < 1:
            raise RuntimeError("原记忆删除失败，更新已取消")

        try:
            insert_result = await asyncio.to_thread(
                vector_db.insert, collection_name, [updated_payload]
            )
            await asyncio.to_thread(vector_db.flush, [collection_name])
            if insert_result.insert_count != 1:
                raise RuntimeError("更新后的记忆插入失败")
        except Exception as update_error:
            rollback_payload = {
                **updated_payload,
                "content": original_content,
                "embedding": original_embedding,
            }
            try:
                rollback_result = await asyncio.to_thread(
                    vector_db.insert, collection_name, [rollback_payload]
                )
                await asyncio.to_thread(vector_db.flush, [collection_name])
                if rollback_result.insert_count != 1:
                    raise RuntimeError("回滚插入未成功")
            except Exception as rollback_error:
                raise RuntimeError(
                    "记忆更新失败且原记录无法恢复，请立即检查向量数据库"
                ) from rollback_error
            raise RuntimeError("记忆更新失败，原内容已恢复") from update_error

        updated_id = (
            str(insert_result.primary_keys[0])
            if insert_result.primary_keys
            else memory_id
        )
        self._invalidate_caches()
        return self._updated_memory_response(memory_id, updated_id, updated_payload)

    @staticmethod
    def _updated_memory_response(
        previous_id: str,
        updated_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "memory_id": updated_id,
            "previous_memory_id": previous_id,
            "id_changed": updated_id != previous_id,
            "content": payload["content"],
            "session_id": payload.get("session_id", ""),
            "persona_id": payload.get("personality_id", ""),
            "create_time": datetime.fromtimestamp(payload["create_time"]).isoformat(),
            "embedding_regenerated": True,
        }

    async def delete_session_memories(self, session_id: str) -> int:
        """
        删除指定会话的所有记忆

        Args:
            session_id: 会话ID

        Returns:
            int: 删除的记忆数量
        """
        try:
            vector_db = self._get_vector_db()
            if not vector_db or not vector_db.is_connected():
                return 0

            collection_name = self.plugin.collection_name
            if not await asyncio.to_thread(
                vector_db.has_collection, collection_name
            ):
                return 0

            # 使用安全的表达式构建方法，避免注入
            try:
                expr = safe_build_milvus_expression("session_id", session_id, "==")
            except ValueError:
                self.logger.warning(
                    f"删除会话记忆失败：session_id 格式无效: {session_id}"
                )
                return 0

            count = await self._count_records(vector_db, collection_name, expr)
            if count is None:
                count = 0
                async for batch in self._iter_query_batches(
                    vector_db,
                    collection_name,
                    expr,
                    ["memory_id"],
                ):
                    count += len(batch)

            # 删除记忆
            if count > 0:
                await asyncio.to_thread(vector_db.delete, collection_name, expr)
                await asyncio.to_thread(vector_db.flush, [collection_name])
                self._invalidate_caches()

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
        now = time.monotonic()
        if (
            self._sessions_cache is not None
            and now - self._sessions_cache_at < MEMORY_SERVICE_CACHE_TTL_SECONDS
        ):
            return self._sessions_cache[:limit]

        try:
            vector_db = self._get_vector_db()
            if not vector_db or not vector_db.is_connected():
                return []

            collection_name = self.plugin.collection_name
            if not await asyncio.to_thread(
                vector_db.has_collection, collection_name
            ):
                return []

            session_data: dict[str, dict[str, Any]] = defaultdict(
                lambda: {
                    "session_id": "",
                    "memory_count": 0,
                    "last_memory_time": None,
                    "first_memory_time": None,
                }
            )

            async for results in self._iter_query_batches(
                vector_db,
                collection_name,
                self._all_records_expr(),
                ["session_id", "create_time"],
            ):
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
                key=lambda x: (
                    x["last_memory_time"] if x["last_memory_time"] else datetime.min
                ),
                reverse=True,
            )

            # 格式化时间
            for session in sessions:
                last_time = session.get("last_memory_time")
                if last_time and isinstance(last_time, datetime):
                    session["last_memory_time"] = last_time.isoformat()

                first_time = session.get("first_memory_time")
                if first_time and isinstance(first_time, datetime):
                    session["first_memory_time"] = first_time.isoformat()

            self._sessions_cache = sessions
            self._sessions_cache_at = time.monotonic()
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
            vector_db = self._get_vector_db()
            if not vector_db or not vector_db.is_connected():
                return []

            collection_name = self.plugin.collection_name
            if not await asyncio.to_thread(
                vector_db.has_collection, collection_name
            ):
                return []

            # 使用embedding模型生成查询向量
            if not getattr(self.plugin, "embedding_provider", None):
                self.logger.warning("Embedding Provider 未初始化，无法进行向量检索")
                return []

            # 生成查询向量
            query_vector = await request_embedding(self.plugin, query)
            if not query_vector:
                return []

            results = await asyncio.to_thread(
                vector_db.search,
                collection_name=collection_name,
                query_vector=query_vector,
                top_k=limit,
                filters=None,
            )

            # 转换结果
            memories = []
            if results:
                for entity in results:
                    try:
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
                            "memory_id": self._record_id(entity),
                            "session_id": entity.get("session_id", ""),
                            "content": entity.get("content", ""),
                            "create_time": create_time.isoformat(),
                            "persona_id": persona_id_value,
                            "similarity_score": entity.get(
                                "_score", entity.get("score", 0.0)
                            ),
                        }
                        memories.append(memory)
                    except Exception as e:
                        self.logger.error(f"转换搜索结果失败: {e}")
                        continue

            return memories

        except Exception as e:
            self.logger.error(f"向量检索失败: {e}", exc_info=True)
            return []
