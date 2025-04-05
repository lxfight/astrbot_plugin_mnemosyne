# -*- coding: utf-8 -*-
"""
Mnemosyne 插件的命令处理函数实现
(注意：装饰器已移除，函数接收 self)
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime

# 导入 AstrBot API 和类型 (仅需要事件和消息段)
from astrbot.api.event import AstrMessageEvent

# 导入必要的模块和常量
from .constants import DEFAULT_COLLECTION_NAME, PRIMARY_FIELD_NAME

# 类型提示
if TYPE_CHECKING:
    from ..main import Mnemosyne


# 注意：函数名加了 _impl 后缀，并接收 self
# 注意：装饰器已移除


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
    confirm: Optional[str] = None,
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
    collection_name: Optional[str] = None,
    limit: int = 5,
    offset: int = 0,
):
    """[实现] 查询指定集合的记忆记录 (按创建时间倒序显示)"""
    if not self.milvus_manager or not self.milvus_manager.is_connected():
        yield event.plain_result("⚠️ Milvus 服务未初始化或未连接。")
        return

    target_collection = collection_name or self.collection_name

    if limit <= 0 or limit > 50:
        yield event.plain_result("⚠️ 查询数量 (limit) 必须在 1 到 50 之间。")
        return
    if offset < 0:
        yield event.plain_result("⚠️ 偏移量 (offset) 不能为负数。")
        return

    try:
        if not self.milvus_manager.has_collection(target_collection):
            yield event.plain_result(f"⚠️ 集合 '{target_collection}' 不存在。")
            return

        # 允许查询超过 16384 范围的实体

        # 检索偏移量的主键字段值
        end_offset = 0 # 结束时的偏移量
        primary_key = 0 # 过滤用的主键字段
        for i in range(5,offset,5):
            end_offset = i
            expr = f"{PRIMARY_FIELD_NAME} > " + str(primary_key)
            output_fields = [PRIMARY_FIELD_NAME]
            self.logger.debug(f"检索第" + str(i) + "个实体的主键字段值")
            records = self.milvus_manager.query(
                collection_name=target_collection,
                expression=expr,
                output_fields=output_fields,
                limit=1,
                offset = 4
            )
            # 更新 primary_key
            primary_key = records.pop().get(PRIMARY_FIELD_NAME)

        # 如果存在偏移量，则更新 primary_key ，否则跳过
        end_offset = offset - end_offset - 1
        if(end_offset > 0):
            expr = f"{PRIMARY_FIELD_NAME} > " + str(primary_key)
            output_fields = [PRIMARY_FIELD_NAME]
            self.logger.debug(f"检索第" + str(offset - 1) + "个实体的主键字段值")
            records = self.milvus_manager.query(
                collection_name=target_collection,
                expression=expr,
                output_fields=output_fields,
                limit=1,
                offset = end_offset
            )
            # 最终的 偏移量的 主键字段值
            # 可以直接用于过滤
            primary_key = records.pop().get(PRIMARY_FIELD_NAME)


        # 使用 检索到的偏移量的主键字段值，以此进行过滤
        expr = f"{PRIMARY_FIELD_NAME} > " + str(primary_key)
        output_fields = [
            "content",
            "create_time",
            "session_id",
            "personality_id",
            PRIMARY_FIELD_NAME,
        ]

        self.logger.debug(
            f"查询集合 '{target_collection}' 记录: expr='{expr}', limit={limit}, output_fields={output_fields}"
        )

        # 已经通过主键字段值进行过滤，无需再使用 offset 偏移
        records = self.milvus_manager.query(
            collection_name=target_collection,
            expression=expr,
            output_fields=output_fields,
            limit=limit,
        )

        if records is None:
            yield event.plain_result(
                f"⚠️ 查询集合 '{target_collection}' 记录失败，请检查日志。"
            )
            return
        if not records:
            yield event.plain_result(
                f"集合 '{target_collection}' 中没有找到任何记忆记录。"
            )
            return

        records.sort(key=lambda x: x.get("create_time", 0), reverse=True)
        paginated_records = records[0 : limit]

        if not paginated_records:
            yield event.plain_result(
                f"在指定的偏移量 {offset} 之后，集合 '{target_collection}' 没有更多记录了。"
            )
            return

        total_found_in_query = len(records)
        response_lines = [
            f"📜 集合 '{target_collection}' 的记忆记录 (显示第 {offset + 1} 到 {offset + len(paginated_records)} 条，按时间倒序):"
        ]
        for i, record in enumerate(paginated_records, start=offset + 1):
            ts = record.get("create_time")
            try:
                time_str = (
                    datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    if ts
                    else "未知时间"
                )
            except (TypeError, ValueError):
                time_str = f"时间戳: {ts}" if ts else "未知时间"
            content = record.get("content", "内容不可用")
            content_preview = content[:200] + ("..." if len(content) > 200 else "")
            session_id = record.get("session_id", "未知会话")
            persona_id = record.get("personality_id", "未知人格")
            pk = record.get(PRIMARY_FIELD_NAME, "未知ID")
            response_lines.append(
                f"#{i} [ID: {pk}]\n"
                f"  时间: {time_str}\n"
                f"  人格: {persona_id}\n"
                f"  会话: {session_id}\n"
                f"  内容: {content_preview}"
            )
        yield event.plain_result("\n\n".join(response_lines))

    except Exception as e:
        self.logger.error(
            f"执行 'memory list_records' 命令失败 (集合: {target_collection}): {str(e)}",
            exc_info=True,
        )
        yield event.plain_result(f"⚠️ 查询记忆记录时发生错误: {str(e)}")


async def delete_session_memory_cmd_impl(
    self: "Mnemosyne",
    event: AstrMessageEvent,
    session_id: str,
    confirm: Optional[str] = None,
):
    """[实现] 删除指定会话 ID 相关的所有记忆信息"""
    if not self.milvus_manager or not self.milvus_manager.is_connected():
        yield event.plain_result("⚠️ Milvus 服务未初始化或未连接。")
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
