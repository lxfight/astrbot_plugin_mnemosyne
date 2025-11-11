"""
Mnemosyne 插件的数据迁移工具
用于运行时自动迁移旧格式的 session_id 到 unified_msg_origin 格式
"""

import asyncio
import time
from typing import TYPE_CHECKING, Any

from pymilvus import Collection

from astrbot.core.log import LogManager

if TYPE_CHECKING:
    from ..main import Mnemosyne

logger = LogManager.GetLogger(__name__)


def _extract_session_uuid(session_id: str | None) -> str | None:
    """
    从 session_id 中提取最后的 UUID 部分

    支持多种格式：
    - 完整 UMO: "platform:type:session_id" → 返回 session_id
    - 带感叹号: "platform!bot!uuid" → 返回 uuid
    - 纯 UUID: "uuid" → 返回 uuid

    Args:
        session_id: session_id 字符串

    Returns:
        提取出的最后部分，如果无法提取则返回原值
    """
    if not session_id:
        return None

    # 按冒号分割（UMO格式）
    if ":" in session_id:
        parts = session_id.split(":")
        session_id = parts[-1]  # 取最后部分

    # 按感叹号分割
    if "!" in session_id:
        parts = session_id.split("!")
        return parts[-1]  # 返回最后部分（UUID）

    # 已经是最简格式
    return session_id


async def migrate_session_data_if_needed(
    plugin: "Mnemosyne",
    unified_msg_origin: str,
    collection_name: str,
) -> None:
    """
    运行时自动迁移：将旧格式的 session_id 更新为 unified_msg_origin 格式

    使用 Milvus 的 upsert 功能进行高效更新

    策略：
    1. 从 unified_msg_origin 解析出各个组成部分
    2. 生成所有可能的旧格式匹配候选（递归拆分）
    3. 在 Milvus 中查询匹配任一候选且不含冒号的旧记录
    4. 使用 upsert 更新记录的 session_id
    5. 标记该会话为已迁移

    Args:
        plugin: Mnemosyne 插件实例
        unified_msg_origin: 完整的统一消息来源（格式：platform:type:session_id）
        collection_name: Milvus 集合名称
    """
    try:
        # 解析 unified_msg_origin
        parts = unified_msg_origin.split(":", 2)
        if len(parts) != 3:
            logger.warning(
                f"[迁移] unified_msg_origin 格式不正确: {unified_msg_origin}"
            )
            return

        platform_id, message_type, full_session_id = parts

        # 生成所有可能的旧格式匹配候选
        candidates = [full_session_id]

        # 按感叹号递归拆分
        if "!" in full_session_id:
            parts_by_bang = full_session_id.split("!")
            for i in range(1, len(parts_by_bang)):
                candidates.append("!".join(parts_by_bang[i:]))

        logger.info(
            f"[迁移] 开始检查会话，候选匹配: {candidates[:3]}..."
        )  # 只显示前3个

        # 检查是否已迁移（使用内存标记）
        if not hasattr(plugin, "_migrated_sessions"):
            plugin._migrated_sessions = set()

        migration_key = unified_msg_origin
        if migration_key in plugin._migrated_sessions:
            # 已迁移过，跳过
            return

        # 确保 Milvus 可用
        if not plugin.milvus_manager or not plugin.milvus_manager.is_connected():
            logger.warning("[迁移] Milvus 不可用，跳过迁移")
            return

        # 查询所有需要迁移的记录
        records_to_migrate = []

        for candidate in candidates:
            try:
                # 构建查询表达式：session_id 等于候选值
                expression = f'session_id == "{candidate}"'

                # 查询记录
                results = plugin.milvus_manager.query(
                    collection_name=collection_name,
                    expression=expression,
                    output_fields=["*"],
                    limit=16384,  # Milvus query 的最大限制
                )

                if results:
                    # 过滤出不包含冒号的记录（旧格式）
                    old_records = [
                        r for r in results if ":" not in r.get("session_id", "")
                    ]
                    if old_records:
                        records_to_migrate.extend(old_records)
                        logger.info(
                            f"[迁移] 找到 {len(old_records)} 条旧格式记录 (session_id={candidate})"
                        )

            except Exception as e:
                logger.error(f"[迁移] 查询候选 {candidate} 时出错: {e}")
                continue

        if not records_to_migrate:
            logger.info(f"[迁移] 未找到需要迁移的旧数据")
            # 标记为已检查
            plugin._migrated_sessions.add(migration_key)
            return

        logger.info(f"[迁移] 共找到 {len(records_to_migrate)} 条旧数据需要迁移")

        # 批量准备更新数据
        records_for_upsert = []
        for record in records_to_migrate:
            # 更新 session_id 字段
            record["session_id"] = unified_msg_origin
            # 添加迁移标记
            if "migrated_at" not in record:
                record["migrated_at"] = int(time.time())
            records_for_upsert.append(record)

        # 使用 upsert 批量更新（Milvus 2.3+）
        try:
            collection = plugin.milvus_manager.get_collection(collection_name)
            if not collection:
                logger.error(f"[迁移] 无法获取集合 '{collection_name}'")
                return

            # 使用 upsert 批量更新
            logger.info(
                f"[迁移] 使用 upsert 批量更新 {len(records_for_upsert)} 条记录..."
            )

            # 检查是否支持 upsert
            if not hasattr(collection, "upsert"):
                error_msg = (
                    "[迁移] 当前 pymilvus 版本不支持 upsert 方法！\n"
                    "请升级 pymilvus 到 2.3.0 或更高版本以支持数据迁移。\n"
                    "升级命令: pip install --upgrade pymilvus>=2.3.0\n"
                    "为保护数据安全，插件将停止运行。"
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            # 执行 upsert
            upsert_result = collection.upsert(data=records_for_upsert)

            if not upsert_result:
                error_msg = "[迁移] Upsert 操作未返回结果，迁移失败"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            migrated_count = upsert_result.upsert_count
            logger.info(f"[迁移] Upsert 成功，更新了 {migrated_count} 条记录")

            # 刷新集合确保数据持久化
            plugin.milvus_manager.flush([collection_name])
            logger.info(f"[迁移] 已刷新集合 '{collection_name}'")

            # 标记为已迁移
            plugin._migrated_sessions.add(migration_key)

            logger.info(
                f"[迁移] 完成！成功更新 {migrated_count} 条记录 -> {unified_msg_origin}"
            )

        except Exception as e:
            logger.error(f"[迁移] 批量更新失败: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"[迁移] 迁移过程失败: {e}", exc_info=True)
