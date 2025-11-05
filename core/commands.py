"""
Mnemosyne 插件的命令处理函数实现
(注意：装饰器已移除，函数接收 self)
"""

from datetime import datetime
from typing import TYPE_CHECKING

# 导入 AstrBot API 和类型 (仅需要事件和消息段)
from astrbot.api.event import AstrMessageEvent

# 导入必要的模块和常量
from .constants import MAX_TOTAL_FETCH_RECORDS, PRIMARY_FIELD_NAME
from .security_utils import safe_build_milvus_expression, validate_session_id

# 类型提示
if TYPE_CHECKING:
    from ..main import Mnemosyne


async def list_collections_cmd_impl(self: "Mnemosyne", event: AstrMessageEvent):
    """[实现] 列出当前 Milvus 实例中的所有集合"""
    if not self.milvus_manager or not self.milvus_manager.is_connected():
        yield event.plain_result("⚠️ Milvus 服务未初始化或未连接。")
        return
    try:
        collections = self.milvus_manager.list_collections()
        if collections is None:
            yield event.plain_result("⚠️ 获取集合列表失败，请检查日志。")
            return
        if not collections:
            response = "当前 Milvus 实例中没有找到任何集合。"
        else:
            response = "当前 Milvus 实例中的集合列表：\n" + "\n".join(
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
    confirm: str | None = None,
):
    """[实现] 删除指定的 Milvus 集合及其所有数据"""
    if not self.milvus_manager or not self.milvus_manager.is_connected():
        yield event.plain_result("⚠️ Milvus 服务未初始化或未连接。")
        return

    is_current_collection = collection_name == self.collection_name
    warning_msg = ""
    if is_current_collection:
        warning_msg = f"\n\n🔥🔥🔥 警告：您正在尝试删除当前插件正在使用的集合 '{collection_name}'！这将导致插件功能异常，直到重新创建或更改配置！ 🔥🔥🔥"

    if confirm != "--confirm":
        yield event.plain_result(
            f"⚠️ 操作确认 ⚠️\n"
            f"此操作将永久删除 Milvus 集合 '{collection_name}' 及其包含的所有数据！此操作无法撤销！\n"
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

        success = self.milvus_manager.drop_collection(collection_name)
        if success:
            msg = f"✅ 已成功删除 Milvus 集合 '{collection_name}'。"
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
                f"⚠️ 删除集合 '{collection_name}' 的请求已发送，但 Milvus 返回失败。请检查 Milvus 日志获取详细信息。"
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
    collection_name: str | None = None,
    limit: int = 5,
):
    """[实现] 查询指定集合的最新记忆记录 (按创建时间倒序，自动获取最新)"""
    if not self.milvus_manager or not self.milvus_manager.is_connected():
        yield event.plain_result("⚠️ Milvus 服务未初始化或未连接。")
        return

    # 获取当前会话的 session_id (如果需要按会话过滤)
    session_id = await self.context.conversation_manager.get_curr_conversation_id(
        event.unified_msg_origin
    )
    # session_id = "session_1" # 如果要测试特定会话或无会话过滤，可以在这里硬编码或设为 None

    target_collection = collection_name or self.collection_name

    # M16 修复: 增强 limit 参数类型和范围验证
    try:
        # 确保 limit 是整数类型
        limit = int(limit)
    except (ValueError, TypeError):
        yield event.plain_result(f"⚠️ limit 参数必须是有效的整数，当前值: {limit}")
        self.logger.warning(
            f"用户提供了无效的 limit 参数: {limit} (类型: {type(limit).__name__})"
        )
        return

    # 验证范围
    if limit <= 0 or limit > 50:
        # 限制用户请求的显示数量
        yield event.plain_result("⚠️ 显示数量 (limit) 必须在 1 到 50 之间。")
        return

    try:
        if not self.milvus_manager.has_collection(target_collection):
            yield event.plain_result(f"⚠️ 集合 '{target_collection}' 不存在。")
            return

        # 构建查询表达式 - 仅基于 session_id (如果需要)
        if session_id:
            # 安全检查：验证 session_id 格式
            if not validate_session_id(session_id):
                yield event.plain_result("⚠️ 会话 ID 格式无效，无法查询记录。")
                self.logger.warning(f"尝试使用无效的 session_id 查询记录: {session_id}")
                return

            # 如果有会话ID，则按会话ID过滤（使用安全的表达式构建）
            try:
                expr = safe_build_milvus_expression("session_id", session_id, "in")
            except ValueError as e:
                yield event.plain_result(f"⚠️ 构建查询表达式失败: {e}")
                self.logger.error(f"构建查询表达式时出错: {e}")
                return

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

        # 重要的修改：移除 Milvus query 的 offset 和 limit 参数，使用总数上限作为 Milvus 的 limit
        fetched_records = self.milvus_manager.query(
            collection_name=target_collection,
            expression=expr,
            output_fields=output_fields,
            limit=MAX_TOTAL_FETCH_RECORDS,  # 使用总数上限作为 Milvus 的 limit
        )

        # 检查查询结果
        if fetched_records is None:
            # 查询失败，milvus_manager.query 通常会返回 None 或抛出异常
            self.logger.error(
                f"查询集合 '{target_collection}' 失败，milvus_manager.query 返回 None。"
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
    confirm: str | None = None,
):
    """[实现] 删除指定会话 ID 相关的所有记忆信息"""
    if not self.milvus_manager or not self.milvus_manager.is_connected():
        yield event.plain_result("⚠️ Milvus 服务未初始化或未连接。")
        return

    if not session_id or not session_id.strip():
        yield event.plain_result("⚠️ 请提供要删除记忆的会话 ID (session_id)。")
        return

    session_id_to_delete = session_id.strip().strip('"`')

    # 安全检查：验证 session_id 格式，防止SQL注入
    if not validate_session_id(session_id_to_delete):
        yield event.plain_result("⚠️ 会话 ID 格式无效，无法执行删除操作。")
        self.logger.warning(f"尝试删除无效的 session_id: {session_id_to_delete}")
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
            self.logger.error(f"构建删除表达式时出错: {e}")
            return

        sender_id = event.get_sender_id()
        self.logger.warning(
            f"管理员 {sender_id} 请求删除会话 '{session_id_to_delete}' 的所有记忆 (集合: {collection_name}, 表达式: '{expr}') (确认执行)"
        )

        mutation_result = self.milvus_manager.delete(
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
                    f"正在刷新 (Flush) 集合 '{collection_name}' 以应用删除操作..."
                )
                self.milvus_manager.flush([collection_name])
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
            yield event.plain_result(
                f"⚠️ 删除会话 ID '{session_id_to_delete}' 记忆的请求失败。请检查 Milvus 日志。"
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
