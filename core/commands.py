# -*- coding: utf-8 -*-
"""
Mnemosyne 插件的命令处理函数实现
(注意：装饰器已移除，函数接收 self)
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime
import asyncio

# 导入 AstrBot API 和类型 (仅需要事件和消息段)
from astrbot.api.event import AstrMessageEvent

# 导入必要的模块和常量
from .constants import PRIMARY_FIELD_NAME, MAX_TOTAL_FETCH_RECORDS

# 导入迁移相关模块
from ..memory_manager.vector_db import VectorDatabaseFactory
from ..memory_manager.embedding_adapter import EmbeddingServiceFactory

# 类型提示
if TYPE_CHECKING:
    from ..main import Mnemosyne


async def list_collections_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 列出当前向量数据库实例中的所有集合"""
    if not self.vector_db or not self.vector_db.is_connected():
        db_type = self.vector_db.get_database_type().value if self.vector_db else "向量数据库"
        yield event.plain_result(f"⚠️ {db_type} 服务未初始化或未连接。")
        return
    try:
        collections = self.vector_db.list_collections()
        if collections is None:
            yield event.plain_result("⚠️ 获取集合列表失败，请检查日志。")
            return
        if not collections:
            db_type = self.vector_db.get_database_type().value
            response = f"当前 {db_type} 实例中没有找到任何集合。"
        else:
            db_type = self.vector_db.get_database_type().value
            response = f"当前 {db_type} 实例中的集合列表：\n" + "\n".join(
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
        self.logger.error(f"执行 'memory list' 命令失败: {str(e)}", exc_info=True)
        yield event.plain_result(f"⚠️ 获取集合列表时出错: {str(e)}")


async def delete_collection_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    collection_name: str,
    confirm: Optional[str] = None,
):
    """[实现] 删除指定的向量数据库集合及其所有数据"""
    if not self.vector_db or not self.vector_db.is_connected():
        db_type = self.vector_db.get_database_type().value if self.vector_db else "向量数据库"
        yield event.plain_result(f"⚠️ {db_type} 服务未初始化或未连接。")
        return

    is_current_collection = collection_name == self.collection_name
    warning_msg = ""
    if is_current_collection:
        warning_msg = f"\n\n🔥🔥🔥 警告：您正在尝试删除当前插件正在使用的集合 '{collection_name}'！这将导致插件功能异常，直到重新创建或更改配置！ 🔥🔥🔥"

    db_type = self.vector_db.get_database_type().value
    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 操作确认 ⚠️\n"
            f"此操作将永久删除 {db_type} 集合 '{collection_name}' 及其包含的所有数据！此操作无法撤销！\n"
            f"{warning_msg}\n\n"
            f"如果您确定要继续，请再次执行命令并添加 `--confirm` 参数:\n"
            f"`/memory drop_collection {collection_name} --confirm`"
        )
        return

    try:
        sender_id = event.get_sender_id()
        self.logger.warning(
            f"管理员 {sender_id} 请求删除集合: {collection_name} (确认执行)"
        )
        if is_current_collection:
            self.logger.critical(
                f"管理员 {sender_id} 正在删除当前插件使用的集合 '{collection_name}'！"
            )

        success = self.vector_db.drop_collection(collection_name)
        if success:
            msg = f"✅ 已成功删除 {db_type} 集合 '{collection_name}'。"
            if is_current_collection:
                msg += "\n插件使用的集合已被删除，请尽快处理！"
            yield event.plain_result(msg)
            self.logger.warning(f"管理员 {sender_id} 成功删除了集合: {collection_name}")
            if is_current_collection:
                self.logger.error(
                    f"插件当前使用的集合 '{collection_name}' 已被删除，相关功能将不可用。"
                )
        else:
            yield event.plain_result(
                f"⚠️ 删除集合 '{collection_name}' 的请求已发送，但 {db_type} 返回失败。请检查日志获取详细信息。"
            )

    except Exception as e:
        self.logger.error(
            f"执行 'memory drop_collection {collection_name}' 命令时发生严重错误: {str(e)}",
            exc_info=True,
        )
        yield event.plain_result(f"⚠️ 删除集合时发生严重错误: {str(e)}")


async def list_records_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    collection_name: Optional[str] = None,
    limit: int = 5,
):
    """[实现] 查询指定集合的最新记忆记录 (按创建时间倒序，自动获取最新)"""
    if not self.vector_db or not self.vector_db.is_connected():
        db_type = self.vector_db.get_database_type().value if self.vector_db else "向量数据库"
        yield event.plain_result(f"⚠️ {db_type} 服务未初始化或未连接。")
        return

    # 获取当前会话的 session_id (如果需要按会话过滤)
    session_id = await self.context.conversation_manager.get_curr_conversation_id(
        event.unified_msg_origin
    )
    # session_id = "session_1" # 如果要测试特定会话或无会话过滤，可以在这里硬编码或设为 None

    target_collection = collection_name or self.collection_name

    # 对用户输入的 limit 进行验证
    if limit <= 0 or limit > 50:
        # 限制用户请求的显示数量
        yield event.plain_result("⚠️ 显示数量 (limit) 必须在 1 到 50 之间。")
        return

    try:
        if not self.vector_db.has_collection(target_collection):
            yield event.plain_result(f"⚠️ 集合 '{target_collection}' 不存在。")
            return

        # 构建查询表达式 - 仅基于 session_id (如果需要)
        if session_id:
            # 如果有会话ID，则按会话ID过滤
            expr = f'session_id in ["{session_id}"]'
            self.logger.info(
                f"将按会话 ID '{session_id}' 过滤并查询所有相关记录 (上限 {MAX_TOTAL_FETCH_RECORDS} 条)。"
            )
        else:
            # 如果没有会话ID上下文，查询所有记录
            expr = f"{PRIMARY_FIELD_NAME} >= 0"
            self.logger.info(
                "未指定会话 ID，将查询集合 '{target_collection}' 中的所有记录 (上限 {MAX_TOTAL_FETCH_RECORDS} 条)。"
            )
            # 或者，如果您的 milvus_manager 支持空表达式查询所有，则 expr = "" 或 None

        # self.logger.debug(f"查询集合 '{target_collection}' 记录: expr='{expr}'") # 上面已有更具体的日志
        output_fields = [
            "content",
            "create_time",
            "session_id",
            "personality_id",
            PRIMARY_FIELD_NAME,
        ]

        self.logger.debug(
            f"准备查询 Milvus: 集合='{target_collection}', 表达式='{expr}', 限制={limit},输出字段={output_fields}, 总数上限={MAX_TOTAL_FETCH_RECORDS}"
        )

        # 直接使用 Milvus 的 offset 和 limit 参数进行分页查询
        # records = self.milvus_manager.query(
        #     collection_name=target_collection,
        #     expression=expr,
        #     output_fields=output_fields,
        #     limit=limit,
        #     offset=offset,  # 直接使用函数参数 offset
        # )

        # 重要的修改：移除向量数据库 query 的 offset 和 limit 参数，使用总数上限作为 limit
        fetched_records = self.vector_db.query(
            collection_name=target_collection,
            expression=expr,
            output_fields=output_fields,
            limit=MAX_TOTAL_FETCH_RECORDS,  # 使用总数上限作为向量数据库的 limit
        )

        # 检查查询结果
        if fetched_records is None:
            # 查询失败，vector_db.query 通常会返回 None 或抛出异常
            self.logger.error(
                f"查询集合 '{target_collection}' 失败，vector_db.query 返回 None。"
            )
            yield event.plain_result(
                f"⚠️ 查询集合 '{target_collection}' 记录失败，请检查日志。"
            )
            return

        if not fetched_records:
            # 查询成功，但没有返回任何记录
            session_filter_msg = f"在会话 '{session_id}' 中" if session_id else ""
            self.logger.info(
                f"集合 '{target_collection}' {session_filter_msg} 没有找到任何匹配的记忆记录。"
            )
            yield event.plain_result(
                f"集合 '{target_collection}' {session_filter_msg} 中没有找到任何匹配的记忆记录。"
            )
            return
        # 检查是否达到了总数上限
        if len(fetched_records) >= MAX_TOTAL_FETCH_RECORDS:
            self.logger.warning(
                f"查询到的记录数量达到总数上限 ({MAX_TOTAL_FETCH_RECORDS})，可能存在更多未获取的记录，导致无法找到更旧的记录，但最新记录应该在获取范围内。"
            )
            yield event.plain_result(
                f"ℹ️ 警告：查询到的记录数量已达到系统获取最新记录的上限 ({MAX_TOTAL_FETCH_RECORDS})。如果记录非常多，可能无法显示更旧的内容，但最新记录应该已包含在内。"
            )

        self.logger.debug(f"成功获取到 {len(fetched_records)} 条原始记录用于排序。")
        # --- 在获取全部结果后进行排序 (按创建时间倒序) ---
        # 这确保了排序是基于所有获取到的记录，找到真正的最新记录
        try:
            # 使用 lambda 表达式按 create_time 字段排序，如果字段不存在或为 None，默认为 0
            fetched_records.sort(
                key=lambda x: x.get("create_time", 0) or 0, reverse=True
            )
            self.logger.debug(
                f"已将获取到的 {len(fetched_records)} 条记录按 create_time 降序排序。"
            )
        except Exception as sort_e:
            self.logger.warning(
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
                self.logger.warning(
                    f"记录 {record.get(PRIMARY_FIELD_NAME, '未知ID')} 的时间戳 '{ts}' 无效或解析错误: {time_e}"
                )
                time_str = f"无效时间戳({ts})" if ts is not None else "未知时间"

            content = record.get("content", "内容不可用")
            # 截断过长的内容以优化显示
            content_preview = content[:200] + ("..." if len(content) > 200 else "")
            record_session_id = record.get("session_id", "未知会话")
            persona_id = record.get("personality_id", "未知人格")
            pk = record.get(PRIMARY_FIELD_NAME, "未知ID")  # 获取主键

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
        self.logger.error(
            f"执行 'memory list_records' 命令时发生意外错误 (集合: {target_collection}): {str(e)}",
            exc_info=True,  # 记录完整的错误堆栈
        )
        yield event.plain_result("⚠️ 查询记忆记录时发生内部错误，请联系管理员。")


async def delete_session_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    session_id: str,
    confirm: Optional[str] = None,
):
    """[实现] 删除指定会话 ID 相关的所有记忆信息"""
    if not self.vector_db or not self.vector_db.is_connected():
        db_type = self.vector_db.get_database_type().value if self.vector_db else "向量数据库"
        yield event.plain_result(f"⚠️ {db_type} 服务未初始化或未连接。")
        return

    if not session_id or not session_id.strip():
        yield event.plain_result("⚠️ 请提供要删除记忆的会话 ID (session_id)。")
        return

    session_id_to_delete = session_id.strip().strip('"`')

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
        expr = f'session_id == "{session_id_to_delete}"'
        sender_id = event.get_sender_id()
        self.logger.warning(
            f"管理员 {sender_id} 请求删除会话 '{session_id_to_delete}' 的所有记忆 (集合: {collection_name}, 表达式: '{expr}') (确认执行)"
        )

        mutation_result = self.vector_db.delete(
            collection_name=collection_name, expression=expr
        )

        if mutation_result:
            delete_pk_count = (
                mutation_result.delete_count
                if hasattr(mutation_result, "delete_count")
                else "未知"
            )
            self.logger.info(
                f"已发送删除会话 '{session_id_to_delete}' 记忆的请求。返回的删除计数（可能不准确）: {delete_pk_count}"
            )
            try:
                self.logger.info(
                    f"正在刷新集合 '{collection_name}' 以应用删除操作..."
                )
                # 对于 FAISS，flush 操作可能不需要，但保持接口一致性
                if hasattr(self.vector_db, 'flush'):
                    self.vector_db.flush([collection_name])
                self.logger.info(f"集合 '{collection_name}' 刷新完成。删除操作已生效。")
                yield event.plain_result(
                    f"✅ 已成功删除会话 ID '{session_id_to_delete}' 的所有记忆信息。"
                )
            except Exception as flush_err:
                self.logger.error(
                    f"刷新集合 '{collection_name}' 以应用删除时出错: {flush_err}",
                    exc_info=True,
                )
                yield event.plain_result(
                    f"⚠️ 已发送删除请求，但在刷新集合使更改生效时出错: {flush_err}。删除可能未完全生效。"
                )
        else:
            db_type = self.vector_db.get_database_type().value
            yield event.plain_result(
                f"⚠️ 删除会话 ID '{session_id_to_delete}' 记忆的请求失败。请检查 {db_type} 日志。"
            )

    except Exception as e:
        self.logger.error(
            f"执行 'memory delete_session_memory' 命令时发生严重错误 (Session ID: {session_id_to_delete}): {str(e)}",
            exc_info=True,
        )
        yield event.plain_result(f"⚠️ 删除会话记忆时发生严重错误: {str(e)}")


async def get_session_id_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 获取当前与您对话的会话 ID"""
    try:
        session_id = await self.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        if session_id:
            yield event.plain_result(f"当前会话 ID: {session_id}")
        else:
            yield event.plain_result(
                "🤔 无法获取当前会话 ID。可能还没有开始对话，或者会话已结束/失效。"
            )
            self.logger.warning(
                f"用户 {event.get_sender_id()} 在 {event.unified_msg_origin} 尝试获取 session_id 失败。"
            )
    except Exception as e:
        self.logger.error(
            f"执行 'memory get_session_id' 命令失败: {str(e)}", exc_info=True
        )
        yield event.plain_result(f"⚠️ 获取当前会话 ID 时发生错误: {str(e)}")


# === 迁移相关命令实现 ===


async def migration_status_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 查看当前插件配置和迁移状态"""
    try:
        # 获取当前配置信息
        current_db_type = self.config.get("vector_database_type", "milvus")
        embedding_provider_id = self.config.get("embedding_provider_id", "")

        # 检查数据库连接状态
        db_status = "❌ 未连接"
        db_info = ""
        if self.vector_db:
            if self.vector_db.is_connected():
                db_status = "✅ 已连接"
                stats = self.vector_db.get_collection_stats(self.collection_name)
                if stats:
                    db_info = f"\n  集合: {self.collection_name}\n  记录数: {stats.get('record_count', 0)}\n  向量维度: {stats.get('vector_dim', 'N/A')}"
            else:
                db_status = "⚠️ 已初始化但未连接"

        # 检查嵌入服务状态
        embedding_status = "❌ 未初始化"
        embedding_info = ""
        if self.embedding_adapter:
            embedding_status = "✅ 已初始化"
            embedding_info = f"\n  服务: {self.embedding_adapter.service_name}\n  模型: {self.embedding_adapter.get_model_name()}\n  维度: {self.embedding_adapter.get_dim()}"

        # 检查是否为新版本配置
        migration_version = self.config.get("_migration_version", "")
        is_migrated = "✅ 已迁移到 v0.6.0" if migration_version else "⚠️ 可能需要迁移"

        response = f"""📊 Mnemosyne 插件状态报告

🔧 配置信息:
  版本: v0.6.0
  数据库类型: {current_db_type}
  嵌入服务ID: {embedding_provider_id or "使用传统配置"}
  迁移状态: {is_migrated}

💾 数据库状态: {db_status}{db_info}

🤖 嵌入服务状态: {embedding_status}{embedding_info}

📝 可用迁移命令:
  /memory migrate_config - 迁移配置到新格式
  /memory migrate_to_faiss - 迁移到 FAISS 数据库
  /memory migrate_to_milvus - 迁移到 Milvus 数据库
  /memory validate_config - 验证当前配置"""

        yield event.plain_result(response)

    except Exception as e:
        self.logger.error(f"获取迁移状态失败: {e}", exc_info=True)
        yield event.plain_result(f"⚠️ 获取状态信息时发生错误: {str(e)}")


async def migrate_config_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 迁移配置到新格式"""
    try:
        # 检查是否已经迁移
        if self.config.get("_migration_version"):
            yield event.plain_result("✅ 配置已经是新格式，无需迁移。")
            return

        yield event.plain_result("🔄 开始迁移配置到新格式...")

        # 添加新的配置项
        if "vector_database_type" not in self.config:
            # 根据现有配置判断数据库类型
            if self.config.get("milvus_lite_path") or self.config.get("address"):
                self.config["vector_database_type"] = "milvus"
                yield event.plain_result(
                    "✓ 检测到 Milvus 配置，设置数据库类型为 milvus"
                )
            else:
                self.config["vector_database_type"] = "faiss"
                yield event.plain_result(
                    "✓ 未检测到 Milvus 配置，设置数据库类型为 faiss"
                )

        # 添加 FAISS 默认配置
        if "faiss_config" not in self.config:
            self.config["faiss_config"] = {}

        faiss_config = self.config["faiss_config"]
        if "faiss_data_path" not in faiss_config:
            faiss_config["faiss_data_path"] = "faiss_data"
        if "faiss_index_type" not in faiss_config:
            faiss_config["faiss_index_type"] = "IndexFlatL2"
        if "faiss_nlist" not in faiss_config:
            faiss_config["faiss_nlist"] = 100

        # 添加嵌入服务提供商ID配置
        if "embedding_provider_id" not in self.config:
            self.config["embedding_provider_id"] = ""

        # 标记迁移版本
        self.config["_migration_version"] = "0.6.0"
        self.config["_migration_date"] = datetime.now().isoformat()

        yield event.plain_result("✅ 配置迁移完成！新增配置项：")
        yield event.plain_result(
            f"  - vector_database_type: {self.config['vector_database_type']}"
        )
        yield event.plain_result(
            f"  - faiss_config.faiss_data_path: {self.config['faiss_config']['faiss_data_path']}"
        )
        yield event.plain_result(
            f"  - faiss_config.faiss_index_type: {self.config['faiss_config']['faiss_index_type']}"
        )
        yield event.plain_result(
            f"  - embedding_provider_id: {self.config['embedding_provider_id']}"
        )
        yield event.plain_result("\n⚠️ 注意：配置已更新，建议重启插件以应用更改。")

    except Exception as e:
        self.logger.error(f"配置迁移失败: {e}", exc_info=True)
        yield event.plain_result(f"⚠️ 配置迁移失败: {str(e)}")


async def migrate_to_faiss_cmd_impl(
    self: "Mnemosyne", event: AstrMessageEvent, confirm: Optional[str] = None
):
    """[实现] 迁移数据到 FAISS 数据库"""
    current_db_type = self.config.get("vector_database_type", "milvus")

    if current_db_type == "faiss":
        yield event.plain_result("✅ 当前已经使用 FAISS 数据库，无需迁移。")
        return

    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 数据库迁移确认 ⚠️\n"
            f"此操作将把数据从 {current_db_type} 迁移到 FAISS 数据库。\n"
            f"迁移过程中可能需要一些时间，请确保：\n"
            f"1. 当前数据库连接正常\n"
            f"2. 有足够的磁盘空间\n"
            f"3. 迁移期间避免其他操作\n\n"
            f"如果确认迁移，请执行：\n"
            f"/memory migrate_to_faiss --confirm"
        )
        return

    try:
        yield event.plain_result("🔄 开始迁移到 FAISS 数据库...")

        # 检查当前数据库连接
        if not self.vector_db or not self.vector_db.is_connected():
            yield event.plain_result("❌ 当前数据库未连接，无法进行迁移。")
            return

        # 创建 FAISS 数据库配置
        current_faiss_config = self.config.get("faiss_config", {})
        faiss_config = {
            "faiss_config": {
                "faiss_data_path": current_faiss_config.get("faiss_data_path", "faiss_data"),
                "faiss_index_type": current_faiss_config.get("faiss_index_type", "IndexFlatL2"),
                "faiss_nlist": current_faiss_config.get("faiss_nlist", 100),
            }
        }

        # 创建目标 FAISS 数据库
        yield event.plain_result("📦 创建 FAISS 数据库实例...")
        target_db = VectorDatabaseFactory.create_database("faiss", faiss_config)
        if not target_db or not target_db.connect():
            yield event.plain_result("❌ 无法创建或连接到 FAISS 数据库。")
            return

        # 执行数据迁移
        yield event.plain_result(f"📋 开始迁移集合 '{self.collection_name}' 的数据...")

        # 在后台执行迁移
        success = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: VectorDatabaseFactory.migrate_data(
                source_db=self.vector_db,
                target_db=target_db,
                collection_name=self.collection_name,
                batch_size=1000,
            ),
        )

        if success:
            # 更新配置
            self.config["vector_database_type"] = "faiss"
            yield event.plain_result("✅ 数据迁移成功！")
            yield event.plain_result("⚠️ 请重启插件以使用新的 FAISS 数据库。")
        else:
            yield event.plain_result("❌ 数据迁移失败，请查看日志获取详细信息。")

        # 断开目标数据库连接
        target_db.disconnect()

    except Exception as e:
        self.logger.error(f"迁移到 FAISS 失败: {e}", exc_info=True)
        yield event.plain_result(f"⚠️ 迁移过程中发生错误: {str(e)}")


async def migrate_to_milvus_cmd_impl(
    self: "Mnemosyne", event: AstrMessageEvent, confirm: Optional[str] = None
):
    """[实现] 迁移数据到 Milvus 数据库"""
    current_db_type = self.config.get("vector_database_type", "milvus")

    if current_db_type == "milvus":
        yield event.plain_result("✅ 当前已经使用 Milvus 数据库，无需迁移。")
        return

    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 数据库迁移确认 ⚠️\n"
            f"此操作将把数据从 {current_db_type} 迁移到 Milvus 数据库。\n"
            f"请确保已正确配置 Milvus 连接信息：\n"
            f"- milvus_lite_path 或 address\n"
            f"- 认证信息（如果需要）\n\n"
            f"如果确认迁移，请执行：\n"
            f"/memory migrate_to_milvus --confirm"
        )
        return

    try:
        yield event.plain_result("🔄 开始迁移到 Milvus 数据库...")

        # 检查当前数据库连接
        if not self.vector_db or not self.vector_db.is_connected():
            yield event.plain_result("❌ 当前数据库未连接，无法进行迁移。")
            return

        # 验证 Milvus 配置
        is_valid, error_msg = VectorDatabaseFactory.validate_config(
            "milvus", self.config
        )
        if not is_valid:
            yield event.plain_result(f"❌ Milvus 配置验证失败: {error_msg}")
            return

        # 创建目标 Milvus 数据库
        yield event.plain_result("📦 创建 Milvus 数据库实例...")
        target_db = VectorDatabaseFactory.create_database("milvus", self.config)
        if not target_db or not target_db.connect():
            yield event.plain_result("❌ 无法创建或连接到 Milvus 数据库。")
            return

        # 执行数据迁移
        yield event.plain_result(f"📋 开始迁移集合 '{self.collection_name}' 的数据...")

        # 在后台执行迁移
        success = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: VectorDatabaseFactory.migrate_data(
                source_db=self.vector_db,
                target_db=target_db,
                collection_name=self.collection_name,
                batch_size=1000,
            ),
        )

        if success:
            # 更新配置
            self.config["vector_database_type"] = "milvus"
            yield event.plain_result("✅ 数据迁移成功！")
            yield event.plain_result("⚠️ 请重启插件以使用新的 Milvus 数据库。")
        else:
            yield event.plain_result("❌ 数据迁移失败，请查看日志获取详细信息。")

        # 断开目标数据库连接
        target_db.disconnect()

    except Exception as e:
        self.logger.error(f"迁移到 Milvus 失败: {e}", exc_info=True)
        yield event.plain_result(f"⚠️ 迁移过程中发生错误: {str(e)}")


async def validate_config_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 验证当前配置"""
    try:
        yield event.plain_result("🔍 开始验证配置...")

        # 验证数据库配置
        db_type = self.config.get("vector_database_type", "milvus")
        db_valid, db_error = VectorDatabaseFactory.validate_config(db_type, self.config)

        if db_valid:
            yield event.plain_result(f"✅ {db_type} 数据库配置验证通过")
        else:
            yield event.plain_result(f"❌ {db_type} 数据库配置验证失败: {db_error}")

        # 验证嵌入服务配置
        embedding_valid, embedding_error = EmbeddingServiceFactory.validate_config(
            self.config
        )

        if embedding_valid:
            yield event.plain_result("✅ 嵌入服务配置验证通过")
        else:
            yield event.plain_result(f"❌ 嵌入服务配置验证失败: {embedding_error}")

        # 检查必要的配置项
        required_fields = ["LLM_providers"]
        missing_fields = [
            field for field in required_fields if not self.config.get(field)
        ]

        if missing_fields:
            yield event.plain_result(f"⚠️ 缺少必要配置: {', '.join(missing_fields)}")
        else:
            yield event.plain_result("✅ 必要配置项检查通过")

        # 总结
        all_valid = db_valid and embedding_valid and not missing_fields
        if all_valid:
            yield event.plain_result("\n🎉 配置验证全部通过！插件应该可以正常工作。")
        else:
            yield event.plain_result("\n⚠️ 发现配置问题，请根据上述提示进行修复。")

    except Exception as e:
        self.logger.error(f"配置验证失败: {e}", exc_info=True)
        yield event.plain_result(f"⚠️ 配置验证过程中发生错误: {str(e)}")


async def help_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 显示帮助信息"""
    # 获取当前数据库类型以提供更准确的帮助信息
    db_type = self.vector_db.get_database_type().value if self.vector_db else "向量数据库"
    help_text = f"""🧠 Mnemosyne 长期记忆插件 v0.6.0
当前数据库: {db_type}

📋 基础命令:
  /memory status - 查看插件状态和配置信息
  /memory get_session_id - 获取当前会话ID
  /memory validate_config - 验证当前配置

📊 记忆管理:
  /memory list - 列出所有集合
  /memory list_records [集合名] [数量] - 查看记忆记录
  /memory reset [--confirm] - 清除当前会话记忆

🔧 迁移工具 (管理员):
  /memory migrate_config - 迁移配置到新格式
  /memory migrate_to_faiss [--confirm] - 迁移到FAISS数据库
  /memory migrate_to_milvus [--confirm] - 迁移到Milvus数据库

🗑️ 数据管理 (管理员):
  /memory drop_collection <集合名> [--confirm] - 删除集合
  /memory delete_session_memory <会话ID> [--confirm] - 删除会话记忆

💡 使用提示:
- 新用户推荐使用 FAISS 数据库（简单高效）
- 企业用户可选择 Milvus 数据库
- 迁移前建议先查看状态：/memory status
- 危险操作需要添加 --confirm 参数确认

🆕 v0.6.0 新功能:
✨ 支持多种向量数据库 (Milvus + FAISS)
✨ 集成AstrBot原生嵌入服务
✨ 一键配置和数据迁移
✨ 改进的错误处理和日志"""

    yield event.plain_result(help_text)
