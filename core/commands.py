# Mnemosyne 插件的命令处理函数实现
# (注意：装饰器已移除，函数接收 self)

import asyncio
import json
import math
import re
import time as time_module
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .constants import MAX_TOTAL_FETCH_RECORDS, PRIMARY_FIELD_NAME, VECTOR_FIELD_NAME
from .security_utils import (
    safe_build_milvus_expression,
    validate_safe_path,
    validate_session_id,
)
from .tools import resolve_max_prompt_chars, truncate_for_embedding

if TYPE_CHECKING:
    from ..main import Mnemosyne


def _get_vector_db(self: "Mnemosyne"):
    return getattr(self, "vector_db", None)


def _build_memory_id_expression(memory_id: str) -> str:
    """
    构建 memory_id 查询表达式。
    """
    normalized = memory_id.strip().strip('"`')
    if not normalized:
        raise ValueError("memory_id 不能为空")
    if len(normalized) > 128:
        raise ValueError("memory_id 长度超过限制")
    if not re.match(r"^[a-zA-Z0-9_-]+$", normalized):
        raise ValueError("memory_id 格式非法，仅允许字母、数字、下划线和连字符")

    try:
        return f"memory_id == {int(normalized)}"
    except ValueError:
        return f'memory_id == "{normalized}"'


def _parse_command_timestamp(value: str, label: str) -> float:
    """Parse a Unix timestamp or ISO 8601 command argument.

    Args:
        value: Timestamp text supplied by a command.
        label: Human-readable argument name for validation errors.

    Returns:
        The parsed Unix timestamp in seconds.

    Raises:
        ValueError: If the value is not a supported timestamp.
    """
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{label}不能为空")
    try:
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized):
            timestamp = float(normalized)
            if not math.isfinite(timestamp):
                raise ValueError("timestamp must be finite")
            return timestamp
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized).timestamp()
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError(
            f"{label}格式无效，请使用 Unix 时间戳、YYYY-MM-DD 或 ISO 8601 日期时间"
        ) from exc


def _query_memory_records(
    self: "Mnemosyne",
    session_id: str | None = None,
    start_timestamp: float | None = None,
    end_timestamp: float | None = None,
) -> tuple[list[dict], bool]:
    """Query and locally filter memory records for administration commands.

    Args:
        self: Mnemosyne plugin instance.
        session_id: Optional session ID. ``None`` queries all sessions.
        start_timestamp: Inclusive lower timestamp bound.
        end_timestamp: Exclusive upper timestamp bound.

    Returns:
        A tuple containing matching records and a safety-limit flag.

    Raises:
        RuntimeError: If the vector database is unavailable.
    """
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        raise RuntimeError("向量数据库未初始化或未连接")

    filters: list[str] = []
    if session_id:
        filters.append(safe_build_milvus_expression("session_id", session_id, "=="))
    if start_timestamp is not None:
        filters.append(
            safe_build_milvus_expression("create_time", start_timestamp, ">=")
        )
    if end_timestamp is not None:
        filters.append(safe_build_milvus_expression("create_time", end_timestamp, "<"))
    expression = " and ".join(filters) if filters else None
    db_type = self.config.get("vector_db_type", "chroma").lower()
    output_fields = ["content", "create_time", "session_id", "personality_id"]
    if db_type == "milvus":
        output_fields.append(PRIMARY_FIELD_NAME)

    records = (
        vector_db.query(
            collection_name=self.collection_name,
            filters=expression,
            output_fields=output_fields,
            limit=MAX_TOTAL_FETCH_RECORDS,
        )
        or []
    )
    reached_limit = len(records) >= MAX_TOTAL_FETCH_RECORDS
    matched_records: list[dict] = []
    for record in records:
        if session_id and record.get("session_id") != session_id:
            continue
        try:
            create_time = float(record.get("create_time"))
        except (TypeError, ValueError):
            continue
        if start_timestamp is not None and create_time < start_timestamp:
            continue
        if end_timestamp is not None and create_time >= end_timestamp:
            continue
        matched_records.append(record)
    return matched_records, reached_limit


def _delete_memory_records(self: "Mnemosyne", records: list[dict]) -> int:
    """Delete records using IDs that match the active vector database backend.

    Args:
        self: Mnemosyne plugin instance.
        records: Records selected for deletion.

    Returns:
        The known number of deleted records reported by the vector database.

    Raises:
        RuntimeError: If the vector database is unavailable before deletion.
        ValueError: If a selected record has no usable native ID.
    """
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        raise RuntimeError("向量数据库未初始化或未连接")

    db_type = self.config.get("vector_db_type", "chroma").lower()
    deleted_count = 0
    for record in records:
        record_id = (
            record.get(PRIMARY_FIELD_NAME) if db_type == "milvus" else record.get("id")
        )
        if record_id is None:
            raise ValueError("查询结果缺少可删除的 memory_id/id")
        expression = (
            _build_memory_id_expression(str(record_id))
            if db_type == "milvus"
            else safe_build_milvus_expression("id", str(record_id), "==")
        )
        result = vector_db.delete(self.collection_name, expression)
        if isinstance(getattr(result, "delete_count", None), int):
            deleted_count += result.delete_count
    vector_db.flush([self.collection_name])
    return deleted_count


def _resolve_memory_export_path(
    self: "Mnemosyne", filename: str, allow_creation: bool
) -> Path:
    """Resolve an export file inside the plugin's exports directory.

    Args:
        self: Mnemosyne plugin instance.
        filename: Relative export filename.
        allow_creation: Whether the parent directory may be created.

    Returns:
        A validated absolute path.

    Raises:
        ValueError: If the plugin data directory or filename is invalid.
    """
    if not getattr(self, "plugin_data_dir", None):
        raise ValueError("插件数据目录未初始化")
    normalized = (filename or "").strip().strip('"`')
    if not normalized:
        raise ValueError("文件名不能为空")
    if not normalized.lower().endswith(".json"):
        normalized += ".json"
    export_dir = Path(self.plugin_data_dir) / "exports"
    return validate_safe_path(
        normalized, str(export_dir), allow_creation=allow_creation
    )


async def list_collections_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 列出当前向量数据库实例中的所有集合"""
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        yield event.plain_result("⚠️ 向量数据库未初始化或未连接。")
        return
    try:
        collections = vector_db.list_collections()
        if collections is None:
            yield event.plain_result("⚠️ 获取集合列表失败，请检查日志。")
            return
        if not collections:
            response = "当前向量数据库中没有找到任何集合。"
        else:
            response = "当前向量数据库中的集合列表：\n" + "\n".join(
                [f"📚 {col}" for col in collections]
            )
            if self.collection_name in collections:
                response += f"\n\n当前插件使用的集合: {self.collection_name}"
            else:
                response += (
                    f"\n\n⚠️ 当前插件配置的集合 '{self.collection_name}' 不在列表中！"
                )
        yield event.plain_result(response)
    except Exception as e:
        logger.error(f"执行 'memory list' 命令失败: {str(e)}", exc_info=True)
        yield event.plain_result(f"⚠️ 获取集合列表时出错: {str(e)}")


async def delete_collection_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    collection_name: str,
    confirm: str | None = None,
):
    """[实现] 删除指定的向量数据库集合及其所有数据"""
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        yield event.plain_result("⚠️ 向量数据库未初始化或未连接。")
        return

    is_current_collection = collection_name == self.collection_name
    warning_msg = ""
    if is_current_collection:
        warning_msg = f"\n\n🔥🔥🔥 警告：您正在尝试删除当前插件正在使用的集合 '{collection_name}'！这将导致插件功能异常，直到重新创建或更改配置！ 🔥🔥🔥"

    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 操作确认 ⚠️\n"
            f"此操作将永久删除向量数据库集合 '{collection_name}' 及其包含的所有数据！此操作无法撤销！\n"
            f"{warning_msg}\n\n"
            f"如果您确定要继续，请再次执行命令并添加 `--confirm` 参数:\n"
            f"`/memory drop_collection {collection_name} --confirm`"
        )
        return

    try:
        sender_id = event.get_sender_id()
        logger.warning(f"管理员 {sender_id} 请求删除集合: {collection_name} (确认执行)")
        if is_current_collection:
            logger.critical(
                f"管理员 {sender_id} 正在删除当前插件使用的集合 '{collection_name}'！"
            )

        success = vector_db.drop_collection(collection_name)
        if success:
            msg = f"✅ 已成功删除向量数据库集合 '{collection_name}'。"
            if is_current_collection:
                msg += "\n插件使用的集合已被删除，请尽快处理！"
            yield event.plain_result(msg)
            logger.warning(f"管理员 {sender_id} 成功删除了集合: {collection_name}")
            if is_current_collection:
                logger.error(
                    f"插件当前使用的集合 '{collection_name}' 已被删除，相关功能将不可用。"
                )
        else:
            yield event.plain_result(
                f"⚠️ 删除集合 '{collection_name}' 的请求已发送，但向量数据库返回失败。请检查日志获取详细信息。"
            )

    except Exception as e:
        logger.error(
            f"执行 'memory drop_collection {collection_name}' 命令时发生严重错误: {str(e)}",
            exc_info=True,
        )
        yield event.plain_result(f"⚠️ 删除集合时发生严重错误: {str(e)}")


async def list_records_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    collection_name: str | None = None,
    limit: int = 5,
):
    """[实现] 查询指定集合的最新记忆记录 (按创建时间倒序，自动获取最新)"""
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        yield event.plain_result("⚠️ 向量数据库未初始化或未连接。")
        return

    # 获取当前会话的 session_id (如果需要按会话过滤)
    # 直接使用 unified_msg_origin 作为 session_id，与存储时保持一致
    session_id = event.unified_msg_origin
    # session_id = "session_1" # 如果要测试特定会话或无会话过滤，可以在这里硬编码或设为 None

    target_collection = collection_name or self.collection_name

    # M16 修复: 增强 limit 参数类型和范围验证
    try:
        # 确保 limit 是整数类型
        limit = int(limit)
    except (ValueError, TypeError):
        yield event.plain_result(f"⚠️ limit 参数必须是有效的整数，当前值: {limit}")
        logger.warning(
            f"用户提供了无效的 limit 参数: {limit} (类型: {type(limit).__name__})"
        )
        return

    # 验证范围
    if limit <= 0 or limit > 50:
        # 限制用户请求的显示数量
        yield event.plain_result("⚠️ 显示数量 (limit) 必须在 1 到 50 之间。")
        return

    try:
        if not vector_db.has_collection(target_collection):
            yield event.plain_result(f"⚠️ 集合 '{target_collection}' 不存在。")
            return

        # 构建查询表达式 - 仅基于 session_id (如果需要)
        if session_id:
            # 安全检查：验证 session_id 格式
            if not validate_session_id(session_id):
                yield event.plain_result("⚠️ 会话 ID 格式无效，无法查询记录。")
                logger.warning(f"尝试使用无效的 session_id 查询记录: {session_id}")
                return

            # 如果有会话ID，则按会话ID过滤（使用安全的表达式构建）
            try:
                expr = safe_build_milvus_expression("session_id", session_id, "==")
            except ValueError as e:
                yield event.plain_result(f"⚠️ 构建查询表达式失败: {e}")
                logger.error(f"构建查询表达式时出错: {e}")
                return

            logger.info(
                f"将按会话 ID '{session_id}' 过滤并查询所有相关记录 (上限 {MAX_TOTAL_FETCH_RECORDS} 条)。"
            )
        else:
            # 如果没有会话ID上下文，查询所有记录
            expr = None
            logger.info(
                "未指定会话 ID，将查询集合 '{target_collection}' 中的所有记录 (上限 {MAX_TOTAL_FETCH_RECORDS} 条)。"
            )
            # 或者，如果您的 milvus_manager 支持空表达式查询所有，则 expr = "" 或 None

        # logger.debug(f"查询集合 '{target_collection}' 记录: expr='{expr}'") # 上面已有更具体的日志
        output_fields = [
            "content",
            "create_time",
            "session_id",
            "personality_id",
            PRIMARY_FIELD_NAME,
        ]

        logger.debug(
            f"准备查询向量数据库: 集合='{target_collection}', 表达式='{expr}', 限制={limit},输出字段={output_fields}, 总数上限={MAX_TOTAL_FETCH_RECORDS}"
        )

        # 直接使用 Milvus 的 offset 和 limit 参数进行分页查询
        # records = self.milvus_manager.query(
        #     collection_name=target_collection,
        #     expression=expr,
        #     output_fields=output_fields,
        #     limit=limit,
        #     offset=offset,  # 直接使用函数参数 offset
        # )

        # 重要的修改：移除 Milvus query 的 offset 和 limit 参数，使用总数上限作为 Milvus 的 limit
        fetched_records = vector_db.query(
            collection_name=target_collection,
            filters=expr,
            output_fields=output_fields,
            limit=MAX_TOTAL_FETCH_RECORDS,  # 使用总数上限作为 Milvus 的 limit
        )

        # 检查查询结果
        if fetched_records is None:
            # 查询失败，milvus_manager.query 通常会返回 None 或抛出异常
            logger.error(
                f"查询集合 '{target_collection}' 失败，milvus_manager.query 返回 None。"
            )
            yield event.plain_result(
                f"⚠️ 查询集合 '{target_collection}' 记录失败，请检查日志。"
            )
            return

        if not fetched_records:
            # 查询成功，但没有返回任何记录
            session_filter_msg = f"在会话 '{session_id}' 中" if session_id else ""
            logger.info(
                f"集合 '{target_collection}' {session_filter_msg} 没有找到任何匹配的记忆记录。"
            )
            yield event.plain_result(
                f"集合 '{target_collection}' {session_filter_msg} 中没有找到任何匹配的记忆记录。"
            )
            return
        # 检查是否达到了总数上限
        if len(fetched_records) >= MAX_TOTAL_FETCH_RECORDS:
            logger.warning(
                f"查询到的记录数量达到总数上限 ({MAX_TOTAL_FETCH_RECORDS})，可能存在更多未获取的记录，导致无法找到更旧的记录，但最新记录应该在获取范围内。"
            )
            yield event.plain_result(
                f"ℹ️ 警告：查询到的记录数量已达到系统获取最新记录的上限 ({MAX_TOTAL_FETCH_RECORDS})。如果记录非常多，可能无法显示更旧的内容，但最新记录应该已包含在内。"
            )

        logger.debug(f"成功获取到 {len(fetched_records)} 条原始记录用于排序。")
        # --- 在获取全部结果后进行排序 (按创建时间倒序) ---
        # 这确保了排序是基于所有获取到的记录，找到真正的最新记录
        try:
            # 使用 lambda 表达式按 create_time 字段排序，如果字段不存在或为 None，默认为 0
            fetched_records.sort(
                key=lambda x: x.get("create_time", 0) or 0, reverse=True
            )
            logger.debug(
                f"已将获取到的 {len(fetched_records)} 条记录按 create_time 降序排序。"
            )
        except Exception as sort_e:
            logger.warning(
                f"对查询结果进行排序时出错: {sort_e}。显示顺序可能不按时间排序。"
            )
            # 如果排序失败，继续处理，但不保证按时间顺序

        # --- 在排序后获取最前的 limit 条记录 ---
        # 从排序后的 fetched_records 中取出最前的 limit 条记录
        display_records = fetched_records[:limit]

        # display_records 不会为空，除非 fetched_records 本身就为空，
        # 而 fetched_records 为空的情况已经在前面处理过了。

        # 准备响应消息
        total_fetched = len(fetched_records)
        display_count = len(display_records)
        # 消息提示用户这是最新的记录
        response_lines = [
            f"📜 集合 '{target_collection}' 的最新记忆记录 (共获取 {total_fetched} 条进行排序, 显示最新的 {display_count} 条):"
        ]

        # 格式化每条记录以供显示
        # 使用 enumerate 从 1 开始生成序号
        for i, record in enumerate(display_records, start=1):
            ts = record.get("create_time")
            try:
                # 根据 Milvus 文档，Query 结果中的 time 是 float 类型的 Unix 时间戳（秒）。
                time_str = (
                    datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    if ts is not None  # 检查 ts 是否存在且不是 None
                    else "未知时间"
                )
            except (TypeError, ValueError, OSError) as time_e:
                # 处理无效或无法解析的时间戳
                logger.warning(
                    f"记录 {record.get(PRIMARY_FIELD_NAME, '未知ID')} 的时间戳 '{ts}' 无效或解析错误: {time_e}"
                )
                time_str = f"无效时间戳({ts})" if ts is not None else "未知时间"

            content = record.get("content", "内容不可用")
            # 截断过长的内容以优化显示
            content_preview = content[:200] + ("..." if len(content) > 200 else "")
            record_session_id = record.get("session_id", "未知会话")
            persona_id = record.get("personality_id", "未知人格")
            pk = record.get(PRIMARY_FIELD_NAME) or record.get(
                "id", "未知ID"
            )  # 获取主键

            response_lines.append(
                f"#{i} [ID: {pk}]\n"  # 使用从 1 开始的序号
                f"  时间: {time_str}\n"
                f"  人格: {persona_id}\n"
                f"  会话: {record_session_id}\n"
                f"  内容: {content_preview}"
            )

        # 发送格式化后的结果
        yield event.plain_result("\n\n".join(response_lines))

    except Exception as e:
        # 捕获所有其他潜在异常
        logger.error(
            f"执行 'memory list_records' 命令时发生意外错误 (集合: {target_collection}): {str(e)}",
            exc_info=True,  # 记录完整的错误堆栈
        )
        yield event.plain_result("⚠️ 查询记忆记录时发生内部错误，请联系管理员。")


async def export_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    filename: str,
    session_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Export selected memory records to a JSON file.

    Args:
        self: Mnemosyne plugin instance.
        event: Event supplying the current session ID.
        filename: JSON filename relative to the exports directory.
        session_id: Session ID or ``--all`` for all sessions.
        start: Inclusive start timestamp.
        end: Exclusive end timestamp.
    """
    try:
        target_session_id = (
            None if session_id == "--all" else session_id or event.unified_msg_origin
        )
        if target_session_id and not validate_session_id(target_session_id):
            yield event.plain_result("会话 ID 格式无效，无法导出记忆。")
            return

        start_timestamp = _parse_command_timestamp(start, "开始时间") if start else None
        end_timestamp = _parse_command_timestamp(end, "结束时间") if end else None
        if (
            start_timestamp is not None
            and end_timestamp is not None
            and start_timestamp >= end_timestamp
        ):
            yield event.plain_result("开始时间必须早于结束时间。")
            return
        records, reached_limit = _query_memory_records(
            self, target_session_id, start_timestamp, end_timestamp
        )
        if reached_limit:
            yield event.plain_result(
                f"匹配记录达到查询上限 {MAX_TOTAL_FETCH_RECORDS} 条，为避免导出不完整，本次未执行。"
            )
            return

        export_path = _resolve_memory_export_path(self, filename, allow_creation=True)
        payload = {
            "format": "mnemosyne-memory-export",
            "version": 1,
            "exported_at": datetime.now().astimezone().isoformat(),
            "collection_name": self.collection_name,
            "records": [
                {
                    "id": record.get("id") or record.get(PRIMARY_FIELD_NAME),
                    "content": record.get("content", ""),
                    "create_time": record.get("create_time"),
                    "session_id": record.get("session_id", ""),
                    "personality_id": record.get("personality_id", ""),
                }
                for record in records
            ],
        }
        export_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        yield event.plain_result(
            f"✅ 导出完成：{export_path}\n"
            f"会话范围：{target_session_id or '全部会话'}\n"
            f"记录数量：{len(records)}"
        )
    except (RuntimeError, ValueError) as exc:
        yield event.plain_result(f"⚠️ 导出记忆失败：{exc}")
    except OSError as exc:
        logger.error(f"Failed to write memory export file: {exc}", exc_info=True)
        yield event.plain_result("⚠️ 导出文件写入失败，请检查插件数据目录权限。")


async def import_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    filename: str,
    confirm: str | None = None,
):
    """Preview or import records from a Mnemosyne JSON export.

    Args:
        self: Mnemosyne plugin instance.
        event: Event used for the response.
        filename: Export filename relative to the exports directory.
        confirm: Must be ``--confirm`` to insert records.
    """
    try:
        import_path = _resolve_memory_export_path(self, filename, allow_creation=False)
        if not import_path.is_file():
            yield event.plain_result(f"⚠️ 导入文件不存在：{import_path}")
            return
        payload = json.loads(import_path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("format") != "mnemosyne-memory-export"
            or payload.get("version") != 1
            or not isinstance(payload.get("records"), list)
        ):
            yield event.plain_result(
                "⚠️ 导入文件格式无效，仅支持 Mnemosyne JSON 导出文件。"
            )
            return
        records = payload["records"]
        if not records:
            yield event.plain_result("导入文件中没有记忆记录。")
            return
        if len(records) >= MAX_TOTAL_FETCH_RECORDS:
            yield event.plain_result(
                f"导入记录达到上限 {MAX_TOTAL_FETCH_RECORDS} 条，本次未执行。"
            )
            return

        normalized_records = []
        for index, record in enumerate(records, start=1):
            if (
                not isinstance(record, dict)
                or not str(record.get("content", "")).strip()
            ):
                yield event.plain_result(f"⚠️ 第 {index} 条记录缺少有效 content。")
                return
            record_session_id = str(record.get("session_id", "")).strip()
            if not validate_session_id(record_session_id):
                yield event.plain_result(f"⚠️ 第 {index} 条记录的 session_id 无效。")
                return
            try:
                create_time = int(float(record.get("create_time")))
            except (TypeError, ValueError):
                yield event.plain_result(f"⚠️ 第 {index} 条记录的 create_time 无效。")
                return
            normalized_records.append(
                {
                    "content": str(record["content"]).strip(),
                    "create_time": create_time,
                    "session_id": record_session_id,
                    "personality_id": str(record.get("personality_id", "")),
                }
            )

        if confirm != "--confirm":
            yield event.plain_result(
                f"将从 {import_path} 导入 {len(normalized_records)} 条记忆。\n"
                "重复导入会产生重复记忆。当前只是预览；确认导入请执行：\n"
                f"/memory import {filename} --confirm"
            )
            return

        embedding_provider = getattr(self, "embedding_provider", None)
        if not embedding_provider:
            yield event.plain_result("⚠️ Embedding Provider 不可用，无法导入记忆。")
            return
        data_to_insert = []
        for record in normalized_records:
            embedding = await embedding_provider.get_embedding(record["content"])
            if not embedding:
                yield event.plain_result("⚠️ 生成 Embedding 失败，未写入任何记录。")
                return
            data_to_insert.append({**record, VECTOR_FIELD_NAME: embedding})

        vector_db = _get_vector_db(self)
        if not vector_db or not vector_db.is_connected():
            yield event.plain_result("⚠️ 向量数据库未初始化或未连接。")
            return
        mutation_result = await asyncio.to_thread(
            vector_db.insert,
            collection_name=self.collection_name,
            data=data_to_insert,
        )
        await asyncio.to_thread(vector_db.flush, [self.collection_name])
        inserted_count = getattr(mutation_result, "insert_count", len(data_to_insert))
        yield event.plain_result(f"✅ 导入完成：成功写入 {inserted_count} 条记忆。")
    except (ValueError, json.JSONDecodeError) as exc:
        yield event.plain_result(f"⚠️ 导入记忆失败：{exc}")
    except OSError as exc:
        logger.error(f"Failed to read memory import file: {exc}", exc_info=True)
        yield event.plain_result("⚠️ 导入文件读取失败，请检查文件权限。")
    except Exception as exc:
        logger.error(f"memory import failed: {exc}", exc_info=True)
        yield event.plain_result(f"⚠️ 导入记忆失败：{exc}")


async def stats_memory_cmd_impl(
    self: "Mnemosyne", event: AstrMessageEvent, session_id: str | None = None
):
    """Show count and time statistics for a session or all sessions.

    Args:
        self: Mnemosyne plugin instance.
        event: Event supplying the current session ID.
        session_id: Session ID or ``--all`` for all sessions.
    """
    try:
        target_session_id = (
            None if session_id == "--all" else session_id or event.unified_msg_origin
        )
        if target_session_id and not validate_session_id(target_session_id):
            yield event.plain_result("会话 ID 格式无效。")
            return
        records, reached_limit = _query_memory_records(self, target_session_id)
        if not records:
            yield event.plain_result("当前范围内没有记忆记录。")
            return
        timestamps = [float(record["create_time"]) for record in records]
        earliest = datetime.fromtimestamp(min(timestamps)).strftime("%Y-%m-%d %H:%M:%S")
        latest = datetime.fromtimestamp(max(timestamps)).strftime("%Y-%m-%d %H:%M:%S")
        sessions = {str(record.get("session_id", "")) for record in records}
        warning = (
            f"\n⚠️ 查询达到上限 {MAX_TOTAL_FETCH_RECORDS} 条，结果可能不完整。"
            if reached_limit
            else ""
        )
        yield event.plain_result(
            f"📊 记忆统计（{target_session_id or '全部会话'}）\n"
            f"记忆数量：{len(records)}\n会话数量：{len(sessions)}\n"
            f"最早时间：{earliest}\n最新时间：{latest}{warning}"
        )
    except (RuntimeError, ValueError, OSError) as exc:
        yield event.plain_result(f"⚠️ 获取记忆统计失败：{exc}")


async def search_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    keyword: str,
    session_id: str | None = None,
    limit: int = 10,
):
    """Search memory content by a case-insensitive substring.

    Args:
        self: Mnemosyne plugin instance.
        event: Event supplying the current session ID.
        keyword: Text to find in memory content.
        session_id: Session ID or ``--all`` for all sessions.
        limit: Maximum number of results to display.
    """
    normalized_keyword = (keyword or "").strip()
    if not normalized_keyword:
        yield event.plain_result("⚠️ 请提供要搜索的关键词。")
        return
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        yield event.plain_result("⚠️ limit 必须是有效整数。")
        return
    if limit <= 0 or limit > 50:
        yield event.plain_result("⚠️ limit 必须在 1 到 50 之间。")
        return
    try:
        target_session_id = (
            None if session_id == "--all" else session_id or event.unified_msg_origin
        )
        if target_session_id and not validate_session_id(target_session_id):
            yield event.plain_result("会话 ID 格式无效。")
            return
        records, reached_limit = _query_memory_records(self, target_session_id)
        matches = [
            record
            for record in records
            if normalized_keyword.casefold()
            in str(record.get("content", "")).casefold()
        ][:limit]
        if not matches:
            yield event.plain_result(f"未找到包含“{normalized_keyword}”的记忆。")
            return
        lines = [f"🔎 找到 {len(matches)} 条匹配记忆："]
        for index, record in enumerate(matches, start=1):
            try:
                time_text = datetime.fromtimestamp(
                    float(record.get("create_time"))
                ).strftime("%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError, OSError):
                time_text = str(record.get("create_time"))
            record_id = record.get("id") or record.get(PRIMARY_FIELD_NAME, "未知")
            content = str(record.get("content", ""))
            preview = content[:200] + ("..." if len(content) > 200 else "")
            lines.append(
                f"#{index} [ID: {record_id}] {time_text}\n"
                f"会话：{record.get('session_id', '未知')}\n内容：{preview}"
            )
        if reached_limit:
            lines.append(
                f"⚠️ 查询达到上限 {MAX_TOTAL_FETCH_RECORDS} 条，结果可能不完整。"
            )
        yield event.plain_result("\n\n".join(lines))
    except (RuntimeError, ValueError, OSError) as exc:
        yield event.plain_result(f"⚠️ 搜索记忆失败：{exc}")


async def delete_between_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    start: str,
    end: str,
    session_id: str | None = None,
    confirm: str | None = None,
):
    """Preview or delete records in a half-open time range.

    Args:
        self: Mnemosyne plugin instance.
        event: Event supplying the current session ID.
        start: Inclusive start timestamp.
        end: Exclusive end timestamp.
        session_id: Optional session ID; defaults to the current session.
        confirm: Must be ``--confirm`` to perform deletion.
    """
    if session_id == "--confirm" and confirm is None:
        confirm, session_id = session_id, None
    target_session_id = session_id or event.unified_msg_origin
    if not target_session_id or not validate_session_id(target_session_id):
        yield event.plain_result("会话 ID 无效，无法按时间范围清理。")
        return
    try:
        start_timestamp = _parse_command_timestamp(start, "开始时间")
        end_timestamp = _parse_command_timestamp(end, "结束时间")
        if start_timestamp >= end_timestamp:
            yield event.plain_result("开始时间必须早于结束时间。")
            return
        records, reached_limit = _query_memory_records(
            self, target_session_id, start_timestamp, end_timestamp
        )
        if reached_limit:
            yield event.plain_result(
                f"匹配记录达到查询上限 {MAX_TOTAL_FETCH_RECORDS} 条，为避免只删除部分记忆，本次未执行。"
            )
            return
        if not records:
            yield event.plain_result("指定时间范围内没有匹配的记忆。")
            return
        if confirm != "--confirm":
            yield event.plain_result(
                f"将删除会话 '{target_session_id}' 在 [{start}, {end}) 内的 "
                f"{len(records)} 条记忆。\n当前只是预览，确认删除请执行：\n"
                f"/memory delete_between {start} {end} {target_session_id} --confirm"
            )
            return
        deleted_count = _delete_memory_records(self, records)
        yield event.plain_result(
            f"✅ 时间范围删除已执行。匹配记录：{len(records)}\n"
            f"向量数据库返回删除数：{deleted_count}"
        )
    except (RuntimeError, ValueError, OSError) as exc:
        logger.error(f"memory delete_between failed: {exc}", exc_info=True)
        yield event.plain_result(f"⚠️ 按时间范围删除记忆失败：{exc}")


async def delete_before_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    cutoff: str,
    session_id: str | None = None,
    confirm: str | None = None,
):
    """Preview or delete records created before a cutoff timestamp.

    Args:
        self: Mnemosyne plugin instance.
        event: Event supplying the current session ID.
        cutoff: ISO 8601 cutoff date or datetime.
        session_id: Optional session ID; defaults to the current session.
        confirm: Must be ``--confirm`` to perform deletion.
    """
    if session_id == "--confirm" and confirm is None:
        confirm, session_id = session_id, None
    target_session_id = session_id or event.unified_msg_origin
    if not target_session_id or not validate_session_id(target_session_id):
        yield event.plain_result("⚠️ 会话 ID 无效，无法执行按时间清理。")
        return
    try:
        cutoff_timestamp = _parse_command_timestamp(cutoff, "截止时间")
        records, reached_limit = _query_memory_records(
            self, target_session_id, end_timestamp=cutoff_timestamp
        )
        if reached_limit:
            yield event.plain_result(
                f"匹配记录达到查询上限 {MAX_TOTAL_FETCH_RECORDS} 条，为避免只删除部分旧记忆，本次未执行。"
            )
            return
        cutoff_display = datetime.fromtimestamp(cutoff_timestamp).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if not records:
            yield event.plain_result(
                f"未找到会话 '{target_session_id}' 在 {cutoff_display} 以前的记忆。"
            )
            return
        if confirm != "--confirm":
            yield event.plain_result(
                f"⚠️ 将删除会话 '{target_session_id}' 在 {cutoff_display} 以前的 "
                f"{len(records)} 条记忆。\n当前只是预览，确认删除请执行：\n"
                f"/memory delete_before {cutoff} {target_session_id} --confirm"
            )
            return
        deleted_count = _delete_memory_records(self, records)
        yield event.plain_result(
            f"✅ 删除请求已执行。会话: {target_session_id}\n"
            f"截止时间: {cutoff_display}\n匹配记录: {len(records)}\n"
            f"向量数据库返回删除数: {deleted_count}"
        )
    except (RuntimeError, ValueError, OSError) as exc:
        logger.error(f"memory delete_before failed: {exc}", exc_info=True)
        yield event.plain_result(f"⚠️ 按时间删除记忆失败：{exc}")


async def delete_session_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    session_id: str,
    confirm: str | None = None,
):
    """[实现] 删除指定会话 ID 相关的所有记忆信息"""
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        yield event.plain_result("⚠️ 向量数据库未初始化或未连接。")
        return

    if not session_id or not session_id.strip():
        yield event.plain_result("⚠️ 请提供要删除记忆的会话 ID (session_id)。")
        return

    session_id_to_delete = session_id.strip().strip('"`')

    # 安全检查：验证 session_id 格式，防止SQL注入
    if not validate_session_id(session_id_to_delete):
        yield event.plain_result("⚠️ 会话 ID 格式无效，无法执行删除操作。")
        logger.warning(f"尝试删除无效的 session_id: {session_id_to_delete}")
        return

    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 操作确认 ⚠️\n"
            f"此操作将永久删除会话 ID '{session_id_to_delete}' 在集合 '{self.collection_name}' 中的所有记忆信息！此操作无法撤销！\n\n"
            f"要确认删除，请再次执行命令并添加 `--confirm` 参数:\n"
            f'`/memory delete_session_memory "{session_id_to_delete}" --confirm`'
        )
        return

    try:
        collection_name = self.collection_name

        # 使用安全的表达式构建方法，防止注入
        try:
            expr = safe_build_milvus_expression(
                "session_id", session_id_to_delete, "=="
            )
        except ValueError as e:
            yield event.plain_result(f"⚠️ 构建删除表达式失败: {e}")
            logger.error(f"构建删除表达式时出错: {e}")
            return

        sender_id = event.get_sender_id()
        logger.warning(
            f"管理员 {sender_id} 请求删除会话 '{session_id_to_delete}' 的所有记忆 (集合: {collection_name}, 表达式: '{expr}') (确认执行)"
        )

        mutation_result = vector_db.delete(collection_name=collection_name, expr=expr)

        if mutation_result:
            delete_pk_count = (
                mutation_result.delete_count
                if hasattr(mutation_result, "delete_count")
                else "未知"
            )
            logger.info(
                f"已发送删除会话 '{session_id_to_delete}' 记忆的请求。返回的删除计数（可能不准确）: {delete_pk_count}"
            )
            try:
                logger.info(
                    f"正在刷新 (Flush) 集合 '{collection_name}' 以应用删除操作..."
                )
                vector_db.flush([collection_name])
                logger.info(f"集合 '{collection_name}' 刷新完成。删除操作已生效。")
                yield event.plain_result(
                    f"✅ 已成功删除会话 ID '{session_id_to_delete}' 的所有记忆信息。"
                )
            except Exception as flush_err:
                logger.error(
                    f"刷新集合 '{collection_name}' 以应用删除时出错: {flush_err}",
                    exc_info=True,
                )
                yield event.plain_result(
                    f"⚠️ 已发送删除请求，但在刷新集合使更改生效时出错: {flush_err}。删除可能未完全生效。"
                )
        else:
            yield event.plain_result(
                f"⚠️ 删除会话 ID '{session_id_to_delete}' 记忆的请求失败。请检查向量数据库日志。"
            )

    except Exception as e:
        logger.error(
            f"执行 'memory delete_session_memory' 命令时发生严重错误 (Session ID: {session_id_to_delete}): {str(e)}",
            exc_info=True,
        )
        yield event.plain_result(f"⚠️ 删除会话记忆时发生严重错误: {str(e)}")


async def delete_record_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    memory_id: str,
    session_id: str | None = None,
    confirm: str | None = None,
):
    """[实现] 删除指定会话中的单条记忆记录"""
    vector_db = _get_vector_db(self)
    if not vector_db or not vector_db.is_connected():
        yield event.plain_result("⚠️ 向量数据库未初始化或未连接。")
        return

    target_session_id = session_id or event.unified_msg_origin
    if not target_session_id or not validate_session_id(target_session_id):
        yield event.plain_result("⚠️ 会话 ID 无效，无法删除指定记录。")
        return

    try:
        memory_expr = _build_memory_id_expression(memory_id)
    except ValueError as e:
        yield event.plain_result(f"⚠️ memory_id 无效: {e}")
        return

    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 操作确认 ⚠️\n"
            f"将删除会话 '{target_session_id}' 中 memory_id={memory_id} 的记忆记录，此操作无法撤销。\n\n"
            f"请使用以下命令确认：\n"
            f'`/memory delete_record "{memory_id}" "{target_session_id}" --confirm`'
        )
        return

    try:
        db_type = self.config.get("vector_db_type", "chroma").lower()
        if db_type == "milvus":
            session_expr = safe_build_milvus_expression(
                "session_id", target_session_id, "=="
            )
            expr = f"{memory_expr} and {session_expr}"
        else:
            # 非 Milvus 后端通常把返回给用户的 ID 存在数据库原生 ID 中。
            expr = f'id == "{memory_id.strip().strip(chr(34)).strip(chr(96))}"'
        mutation_result = vector_db.delete(
            collection_name=self.collection_name,
            expr=expr,
        )
        if not mutation_result:
            yield event.plain_result("⚠️ 删除请求失败，请检查向量数据库日志。")
            return

        delete_count = (
            mutation_result.delete_count
            if hasattr(mutation_result, "delete_count")
            else "未知"
        )
        vector_db.flush([self.collection_name])
        yield event.plain_result(
            f"✅ 删除请求已执行。会话: {target_session_id}\n"
            f"记录 ID: {memory_id}\n"
            f"向量数据库返回删除计数: {delete_count}"
        )
    except Exception as e:
        logger.error(
            f"执行 'memory delete_record' 失败 (memory_id={memory_id}, session={target_session_id}): {e}",
            exc_info=True,
        )
        yield event.plain_result(f"⚠️ 删除指定记录失败: {e}")


async def remember_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    content: str,
):
    """[实现] 手动写入一条长期记忆"""
    memory_content = content.strip() if isinstance(content, str) else ""
    if not memory_content:
        yield event.plain_result("⚠️ 请提供要记住的内容。")
        return

    max_chars = resolve_max_prompt_chars(getattr(self, "config", None), default=4000)
    memory_content, memory_was_truncated = truncate_for_embedding(
        memory_content,
        max_chars,
        append_suffix=False,
    )
    if memory_was_truncated:
        logger.info(
            f"'memory remember' 输入超长，已按 max_prompt_chars_for_embedding={max_chars} 截断。"
        )

    try:
        from . import memory_operations

        success = await memory_operations.store_manual_memory(
            plugin=self,
            event=event,
            memory_content=memory_content,
            source="memory_command",
        )
        if success:
            yield event.plain_result(
                f"✅ 已写入长期记忆：{memory_content[:120]}"
                f"{'...' if len(memory_content) > 120 else ''}"
            )
        else:
            yield event.plain_result("⚠️ 写入长期记忆失败，请检查日志。")
    except Exception as e:
        logger.error(f"执行 'memory remember' 命令失败: {e}", exc_info=True)
        yield event.plain_result(f"⚠️ 写入长期记忆失败: {e}")


async def get_session_id_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 获取当前与您对话的会话 ID"""
    try:
        # 直接使用 unified_msg_origin 作为 session_id，与存储时保持一致
        session_id = event.unified_msg_origin
        if session_id:
            yield event.plain_result(f"当前会话 ID: {session_id}")
        else:
            yield event.plain_result(
                "🤔 无法获取当前会话 ID。可能还没有开始对话，或者会话已结束/失效。"
            )
            logger.warning(
                f"用户 {event.get_sender_id()} 在 {event.unified_msg_origin} 尝试获取 session_id 失败。"
            )
    except Exception as e:
        logger.error(f"执行 'memory get_session_id' 命令失败: {str(e)}", exc_info=True)
        yield event.plain_result(f"⚠️ 获取当前会话 ID 时发生错误: {str(e)}")


async def init_memory_system_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    force: str | None = None,
):
    """[实现] 初始化或重新初始化记忆系统"""
    vector_db = _get_vector_db(self)
    if not vector_db:
        yield event.plain_result("⚠️ 向量数据库服务未初始化。")
        return

    # 尝试确保连接 - 向量数据库使用延迟连接，首次操作时才会真正连接
    try:
        # 通过调用一个轻量级操作来触发连接（如果尚未连接）
        if not vector_db.is_connected():
            # 尝试连接
            vector_db.list_collections()
    except Exception as e:
        logger.error(f"尝试连接向量数据库失败: {e}")
        yield event.plain_result(
            f"⚠️ 无法连接到向量数据库服务: {e}\n请检查数据库配置和服务状态。"
        )
        return

    try:
        # 检查 embedding provider 是否就绪
        if not self.embedding_provider or not self._embedding_provider_ready:
            yield event.plain_result(
                "⚠️ Embedding Provider 尚未就绪。\n"
                "请确保已在 AstrBot 中配置并启用 Embedding Provider。\n"
                "配置完成后请重试此命令。"
            )
            return

        # 获取当前 embedding 维度
        current_dim = None
        try:
            current_dim = getattr(self.embedding_provider, "embedding_dim", None)
            if not current_dim and callable(
                getattr(self.embedding_provider, "get_dim", None)
            ):
                current_dim = self.embedding_provider.get_dim()
        except Exception as e:
            logger.error(f"获取 embedding 维度失败: {e}")
            yield event.plain_result(f"⚠️ 无法获取 Embedding Provider 的维度信息: {e}")
            return

        if not current_dim or not isinstance(current_dim, int) or current_dim <= 0:
            yield event.plain_result(
                f"⚠️ Embedding Provider 返回的维度无效: {current_dim}\n"
                "请检查 Embedding Provider 配置。"
            )
            return

        collection_name = self.collection_name
        db_type = self.config.get("vector_db_type", "chroma").lower()

        if db_type != "milvus":
            self.config["embedding_dim"] = current_dim
            from . import initialization

            initialization.initialize_config_and_schema(self)
            initialization.setup_vector_db_collection_and_index(
                self, skip_if_not_ready=False
            )
            yield event.plain_result(
                f"✅ 已确认集合 '{collection_name}' 可用 (维度: {current_dim})\n"
                f"当前向量数据库后端: {db_type}"
            )
            return

        if not self.milvus_manager:
            yield event.plain_result(
                "⚠️ Milvus 管理器未初始化，无法执行 Milvus 专用迁移。"
            )
            return

        needs_migration = False
        old_dim = None

        # 检查集合是否已存在
        if self.milvus_manager.has_collection(collection_name):
            # 检查现有集合的维度
            collection = self.milvus_manager.get_collection(collection_name)
            if collection:
                for field in collection.schema.fields:
                    if field.name == "embedding":  # 向量字段名
                        old_dim = field.params.get("dim")
                        if old_dim != current_dim:
                            needs_migration = True
                            logger.warning(
                                f"检测到维度不匹配: 集合维度={old_dim}, 模型维度={current_dim}"
                            )
                        break

            if needs_migration:
                if force != "--force":
                    yield event.plain_result(
                        f"⚠️ 维度不匹配警告 ⚠️\n\n"
                        f"现有集合 '{collection_name}' 的向量维度为 {old_dim}\n"
                        f"当前 Embedding Provider 的维度为 {current_dim}\n\n"
                        f"需要重新初始化集合以匹配新维度。\n"
                        f"旧数据的文本内容将被保留并使用新维度重新生成向量。\n\n"
                        f"⚠️ 此操作将：\n"
                        f"1. 备份当前集合的文本数据\n"
                        f"2. 删除旧集合\n"
                        f"3. 创建新集合（使用新维度）\n"
                        f"4. 重新生成向量并导入数据\n\n"
                        f"如果确认执行，请运行:\n"
                        f"`/memory init --force`"
                    )
                    return

                # 执行数据迁移
                yield event.plain_result(
                    f"🔄 开始迁移数据...\n从维度 {old_dim} 迁移到 {current_dim}"
                )

                # 检查插件数据目录
                if not self.plugin_data_dir:
                    yield event.plain_result("⚠️ 无法获取插件数据目录，迁移中止")
                    logger.error("plugin_data_dir 未初始化，无法进行备份")
                    return

                # 创建备份目录

                backup_dir = Path(self.plugin_data_dir) / "backups"
                try:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    yield event.plain_result(f"⚠️ 无法创建备份目录: {e}，迁移中止")
                    logger.error(f"创建备份目录失败: {e}")
                    return

                timestamp = int(time_module.time())
                backup_file = (
                    backup_dir
                    / f"memory_backup_{collection_name}_{old_dim}to{current_dim}_{timestamp}.json"
                )

                # 分批导出旧数据
                logger.info(f"开始分批导出集合 '{collection_name}' 的所有数据...")
                yield event.plain_result("📦 正在分批导出所有记忆数据...")

                all_records = []
                batch_size = 16384  # Milvus 单次查询上限
                offset = 0

                try:
                    while True:
                        batch_records = self.milvus_manager.query(
                            collection_name=collection_name,
                            expression=f"{PRIMARY_FIELD_NAME} >= 0",
                            output_fields=[
                                "content",
                                "create_time",
                                "session_id",
                                "personality_id",
                            ],
                            limit=batch_size,
                            offset=offset,
                        )

                        if not batch_records:
                            break

                        all_records.extend(batch_records)
                        offset += len(batch_records)

                        logger.info(f"已导出 {len(all_records)} 条记录...")

                        # 如果本批次少于batch_size，说明已经到达末尾
                        if len(batch_records) < batch_size:
                            break

                    if not all_records:
                        logger.warning("旧集合中没有数据，将创建新集合。")

                except Exception as e:
                    logger.error(f"导出旧数据失败: {e}")
                    yield event.plain_result(f"⚠️ 导出旧数据失败: {e}，迁移中止")
                    return

                record_count = len(all_records)

                # 保存备份到文件 - 备份失败则终止整个操作
                try:
                    backup_data = {
                        "collection_name": collection_name,
                        "old_dimension": old_dim,
                        "new_dimension": current_dim,
                        "timestamp": timestamp,
                        "record_count": record_count,
                        "records": all_records,
                    }
                    with open(backup_file, "w", encoding="utf-8") as f:
                        json.dump(backup_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"已将 {record_count} 条记录备份到: {backup_file}")
                    yield event.plain_result(
                        f"✅ 已导出并备份 {record_count} 条记录\n"
                        f"备份文件: {backup_file.name}"
                    )
                except Exception as e:
                    logger.error(f"保存备份文件失败: {e}")
                    yield event.plain_result(
                        f"⚠️ 保存备份文件失败: {e}\n"
                        f"为保证数据安全，迁移操作已终止。\n"
                        f"请检查磁盘空间和文件权限后重试。"
                    )
                    return

                old_records = all_records

                # 删除旧集合
                logger.info(f"删除旧集合 '{collection_name}'...")
                if not self.milvus_manager.drop_collection(collection_name):
                    yield event.plain_result("⚠️ 删除旧集合失败")
                    return
                yield event.plain_result("✅ 已删除旧集合")

                # 更新 schema 并创建新集合
                logger.info("更新 schema 并创建新集合...")
                self.config["embedding_dim"] = current_dim

                # 重新初始化 schema
                from . import initialization

                initialization.initialize_config_and_schema(self)

                # 创建新集合
                initialization.setup_milvus_collection_and_index(
                    self, skip_if_not_ready=False
                )
                yield event.plain_result(f"✅ 已创建新集合（维度: {current_dim}）")

                # 重新生成向量并导入
                if old_records:
                    yield event.plain_result(
                        f"🔄 正在重新生成 {record_count} 条记录的向量..."
                    )
                    success_count = 0
                    fail_count = 0

                    for i, record in enumerate(old_records):
                        try:
                            content = record.get("content", "")
                            if not content:
                                continue

                            # 生成新向量
                            embedding = await self.embedding_provider.get_embedding(
                                content
                            )
                            if not embedding:
                                fail_count += 1
                                continue

                            # 插入新记录 - 使用类型标注避免 Pylance 错误
                            insert_data: list = [
                                {
                                    "personality_id": record.get("personality_id", ""),
                                    "session_id": record.get("session_id", ""),
                                    "content": content,
                                    "embedding": embedding,
                                    "create_time": record.get(
                                        "create_time", int(datetime.now().timestamp())
                                    ),
                                }
                            ]

                            result = self.milvus_manager.insert(
                                collection_name, insert_data
                            )
                            if result:
                                success_count += 1
                            else:
                                fail_count += 1

                            # 每10条记录报告一次进度
                            if (i + 1) % 10 == 0:
                                yield event.plain_result(
                                    f"进度: {i + 1}/{record_count} "
                                    f"(成功: {success_count}, 失败: {fail_count})"
                                )

                        except Exception as e:
                            logger.error(f"处理记录 {i} 时出错: {e}")
                            fail_count += 1

                    # Flush 确保数据持久化
                    self.milvus_manager.flush([collection_name])

                    yield event.plain_result(
                        f"✅ 数据迁移完成！\n"
                        f"成功: {success_count} 条\n"
                        f"失败: {fail_count} 条\n"
                        f"新维度: {current_dim}"
                    )
                else:
                    yield event.plain_result("✅ 迁移完成（无旧数据）")

            else:
                # 维度匹配，无需迁移
                yield event.plain_result(
                    f"✅ 集合 '{collection_name}' 已存在且维度匹配 ({current_dim})。\n"
                    "无需重新初始化。"
                )
        else:
            # 集合不存在，创建新集合
            yield event.plain_result(f"📝 集合 '{collection_name}' 不存在，正在创建...")

            self.config["embedding_dim"] = current_dim
            from . import initialization

            initialization.initialize_config_and_schema(self)
            initialization.setup_milvus_collection_and_index(
                self, skip_if_not_ready=False
            )

            yield event.plain_result(
                f"✅ 已成功创建集合 '{collection_name}' (维度: {current_dim})\n"
                "记忆系统已就绪！"
            )

    except Exception as e:
        logger.error(f"执行 'memory init' 命令失败: {str(e)}", exc_info=True)
        yield event.plain_result(f"⚠️ 初始化失败: {str(e)}")
