"""Runtime migration for legacy Milvus session identifiers."""

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING

from astrbot.core.log import LogManager

from .security_utils import safe_build_milvus_expression

if TYPE_CHECKING:
    from ..main import Mnemosyne

logger = LogManager.GetLogger(__name__)

MIGRATION_CHECKED_LIMIT = 4096
MIGRATION_QUERY_LIMIT = 16384
MIGRATION_UPSERT_BATCH_SIZE = 200


def _get_migrated_sessions(plugin: "Mnemosyne") -> OrderedDict[str, None]:
    sessions = getattr(plugin, "_migrated_sessions", None)
    if sessions is None:
        sessions = OrderedDict()
        plugin._migrated_sessions = sessions
    return sessions


def _get_inflight_sessions(plugin: "Mnemosyne") -> set[str]:
    sessions = getattr(plugin, "_migration_inflight", None)
    if sessions is None:
        sessions = set()
        plugin._migration_inflight = sessions
    return sessions


def _mark_migration_checked(plugin: "Mnemosyne", migration_key: str) -> None:
    sessions = _get_migrated_sessions(plugin)
    sessions[migration_key] = None
    sessions.move_to_end(migration_key)
    while len(sessions) > MIGRATION_CHECKED_LIMIT:
        sessions.popitem(last=False)


def _build_session_candidates(unified_msg_origin: str) -> list[str] | None:
    parts = unified_msg_origin.split(":", 2)
    if len(parts) != 3:
        logger.warning(f"[迁移] unified_msg_origin 格式不正确: {unified_msg_origin}")
        return None

    full_session_id = parts[2]
    candidates = [full_session_id]
    if "!" in full_session_id:
        parts_by_bang = full_session_id.split("!")
        for index in range(1, len(parts_by_bang)):
            candidates.append("!".join(parts_by_bang[index:]))
    return candidates


def _migrate_session_data_sync(
    plugin: "Mnemosyne",
    unified_msg_origin: str,
    collection_name: str,
) -> bool:
    """Run the blocking Milvus migration outside the event loop."""
    candidates = _build_session_candidates(unified_msg_origin)
    if candidates is None:
        return True

    manager = getattr(plugin, "milvus_manager", None)
    if not manager or not manager.is_connected():
        logger.warning("[迁移] Milvus 不可用，跳过迁移")
        return False

    try:
        expressions = [
            safe_build_milvus_expression("session_id", candidate, "==")
            for candidate in candidates
        ]
        expression = " or ".join(f"({item})" for item in expressions)
        results = manager.query(
            collection_name=collection_name,
            expression=expression,
            # Milvus upsert replaces the full entity, so all fields are required.
            output_fields=["*"],
            limit=MIGRATION_QUERY_LIMIT,
        )
    except Exception as exc:
        logger.error(f"[迁移] 查询旧会话数据失败: {exc}", exc_info=True)
        return False

    if results is None:
        return False

    records = [
        record
        for record in results
        if ":" not in record.get("session_id", "")
        and record.get("session_id") != unified_msg_origin
    ]
    if not records:
        logger.info("[迁移] 未找到需要迁移的旧数据")
        return True

    collection = manager.get_collection(collection_name)
    if not collection:
        logger.error(f"[迁移] 无法获取集合 '{collection_name}'")
        return False
    if not hasattr(collection, "upsert"):
        logger.error("[迁移] 当前 pymilvus 版本不支持 upsert，请升级到 2.3.0+")
        return False

    for record in records:
        record["session_id"] = unified_msg_origin

    migrated_count = 0
    try:
        for start in range(0, len(records), MIGRATION_UPSERT_BATCH_SIZE):
            batch = records[start : start + MIGRATION_UPSERT_BATCH_SIZE]
            result = collection.upsert(data=batch)
            if not result:
                logger.error("[迁移] Upsert 操作未返回结果，迁移失败")
                return False
            migrated_count += getattr(result, "upsert_count", len(batch)) or 0

        manager.flush([collection_name])
    except Exception as exc:
        logger.error(f"[迁移] 批量更新失败: {exc}", exc_info=True)
        return False

    truncated = len(results) >= MIGRATION_QUERY_LIMIT
    logger.info(
        f"[迁移] 已更新 {migrated_count} 条记录 -> {unified_msg_origin}"
        + ("（达到单次查询上限，稍后继续）" if truncated else "")
    )
    # A truncated query must stay eligible so the next request can migrate the rest.
    return not truncated


async def migrate_session_data_if_needed(
    plugin: "Mnemosyne",
    unified_msg_origin: str,
    collection_name: str,
) -> None:
    """Migrate one session once, without blocking the event loop."""
    migration_key = unified_msg_origin
    if migration_key in _get_migrated_sessions(plugin):
        return

    inflight = _get_inflight_sessions(plugin)
    if migration_key in inflight:
        logger.debug(f"[迁移] 会话 {migration_key} 已有迁移任务运行，跳过重复提交")
        return

    inflight.add(migration_key)
    try:
        checked = await asyncio.to_thread(
            _migrate_session_data_sync,
            plugin,
            unified_msg_origin,
            collection_name,
        )
        if checked:
            _mark_migration_checked(plugin, migration_key)
    except Exception as exc:
        logger.error(f"[迁移] 迁移过程失败: {exc}", exc_info=True)
    finally:
        inflight.discard(migration_key)
