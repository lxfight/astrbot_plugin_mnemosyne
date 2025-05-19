# -*- coding: utf-8 -*-
"""
Mnemosyne - 基于 RAG 的 AstrBot 长期记忆插件主文件
负责插件注册、初始化流程调用、事件和命令的绑定。
"""

import asyncio
from typing import List, Optional, Union
import re

# --- AstrBot 核心导入 ---
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import PermissionType, permission_type
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *  # 导入 AstrBot API
from astrbot.api.message_components import *  # 导入消息组件
from astrbot.core.log import LogManager
from astrbot.api.provider import LLMResponse, ProviderRequest

# --- 插件内部模块导入 ---
from .core import initialization  # 导入初始化逻辑模块
from .core import memory_operations  # 导入记忆操作逻辑模块
from .core import commands  # 导入命令处理实现模块
from .core.constants import *  # 导入所有常量
from .core.tools import is_group_chat

# --- 类型定义和依赖库 ---
from pymilvus import CollectionSchema
from .memory_manager.message_counter import MessageCounter
from .memory_manager.vector_db.milvus_manager import MilvusManager
from .memory_manager.embedding import OpenAIEmbeddingAPI, GeminiEmbeddingAPI
from .memory_manager.context_manager import ConversationContextManager



@register(
    "Mnemosyne",
    "lxfight",
    "一个AstrBot插件，实现基于RAG技术的长期记忆功能。",
    "0.4.0",
    "https://github.com/lxfight/astrbot_plugin_mnemosyne",
)
class Mnemosyne(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.context = context
        self.logger = LogManager.GetLogger(log_name="Mnemosyne")

        # --- 初始化核心组件状态 ---
        self.collection_schema: Optional[CollectionSchema] = None
        self.index_params: dict = {}
        self.search_params: dict = {}
        self.output_fields_for_query: List[str] = []
        self.collection_name: str = DEFAULT_COLLECTION_NAME
        self.milvus_manager: Optional[MilvusManager] = None
        self.msg_counter: Optional[MessageCounter] = None
        self.context_manager: Optional[ConversationContextManager] = None
        self.ebd: Optional[Union[OpenAIEmbeddingAPI, GeminiEmbeddingAPI,Star]] = None
        self.provider = None

        # 初始化嵌入服务
        try:
            self.ebd = self.context.get_registered_star("astrbot_plugin_embedding_adapter").star_cls
            dim=self.ebd.get_dim()
            modele_name=self.ebd.get_model_name()
            if dim is not None and modele_name is not None:
                self.config["embedding_dim"] = dim
                self.config["collection_name"] = "ea_"+re.sub(r'[^a-zA-Z0-9]', '_', modele_name)
            else:
                raise ValueError("嵌入服务适配器未正确注册或未返回有效的维度和模型名称。")
        except Exception as e:
            self.logger.warning(f"嵌入服务适配器插件加载失败: {e}", exc_info=True)
            self.ebd = None
        if self.ebd is None:
            embedding_service = config.get("embedding_service", "openai").lower()
            if embedding_service == "gemini":
                self.ebd = GeminiEmbeddingAPI(
                    model=config.get("embedding_model", "gemini-embedding-exp-03-07"),
                    api_key=config.get("embedding_key"),
                )
                self.logger.info("已选择 Gemini 作为嵌入服务提供商")
            else:
                self.ebd = OpenAIEmbeddingAPI(
                    model=config.get("embedding_model", "text-embedding-3-small"),
                    api_key=config.get("embedding_key"),
                    base_url=config.get("embedding_url"),
                )
                self.logger.info("已选择 OpenAI 作为嵌入服务提供商")

        # --- 一个该死的计时器 ---
        self._summary_check_task: Optional[asyncio.Task] = None

        summary_check_config = config.get("summary_check_task")
        self.summary_check_interval: int = summary_check_config.get(
            "SUMMARY_CHECK_INTERVAL_SECONDS", DEFAULT_SUMMARY_CHECK_INTERVAL_SECONDS
        )
        self.summary_time_threshold: int = summary_check_config.get(
            "SUMMARY_TIME_THRESHOLD_SECONDS", DEFAULT_SUMMARY_TIME_THRESHOLD_SECONDS
        )
        if self.summary_time_threshold <= 0:
            self.logger.warning(
                f"配置的 SUMMARY_TIME_THRESHOLD_SECONDS ({self.summary_time_threshold}) 无效，将禁用基于时间的自动总结。"
            )
            self.summary_time_threshold = float("inf")
        # 是否需要刷新
        self.flush_after_insert = False

        self.logger.info("开始初始化 Mnemosyne 插件...")
        try:
            initialization.initialize_config_check(self)
            initialization.initialize_config_and_schema(self)  # 初始化配置和schema
            initialization.initialize_milvus(self)  # 初始化 Milvus
            initialization.initialize_components(self)  # 初始化核心组件
            # --- 启动后台总结检查任务 ---
            if self.context_manager and self.summary_time_threshold != float("inf"):
                # 确保 context_manager 已初始化且阈值有效
                self._summary_check_task = asyncio.create_task(
                    memory_operations._periodic_summarization_check(self)
                )
                self.logger.info("后台总结检查任务已启动。")
            elif self.summary_time_threshold == float("inf"):
                self.logger.info("基于时间的自动总结已禁用，不启动后台检查任务。")
            else:
                self.logger.warning(
                    "Context manager 未初始化，无法启动后台总结检查任务。"
                )

            self.logger.info("Mnemosyne 插件核心组件初始化成功。")
        except Exception as e:
            self.logger.critical(
                f"Mnemosyne 插件初始化过程中发生严重错误，插件可能无法正常工作: {e}",
                exc_info=True,
            )

    # --- 事件处理钩子 (调用 memory_operations.py 中的实现) ---
    @filter.on_llm_request()
    async def query_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """[事件钩子] 在 LLM 请求前，查询并注入长期记忆。"""
        # 当会话第一次发生时，插件会从AstrBot中获取上下文历史，之后的会话历史由插件自动管理
        try:
            if not self.provider:
                provider_id = self.config.get("LLM_providers", "")
                self.provider = self.context.get_provider_by_id(provider_id)

            await memory_operations.handle_query_memory(self, event, req)
        except Exception as e:
            self.logger.error(
                f"处理 on_llm_request 钩子时发生捕获异常: {e}", exc_info=True
            )
        return

    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        """[事件钩子] 在 LLM 响应后"""
        try:
            await memory_operations.handle_on_llm_resp(self, event, resp)
        except Exception as e:
            self.logger.error(
                f"处理 on_llm_response 钩子时发生捕获异常: {e}", exc_info=True
            )
        return

    # --- 命令处理 (定义方法并应用装饰器，调用 commands.py 中的实现) ---

    @command_group("memory")
    def memory_group(self):
        """长期记忆管理命令组 /memory"""
        # 这个方法体是空的，主要是为了定义组
        pass

    # 应用装饰器，并调用实现函数
    @memory_group.command("list")  # type: ignore
    async def list_collections_cmd(self, event: AstrMessageEvent):
        """列出当前 Milvus 实例中的所有集合 /memory list
        使用示例：/memory list
        """
        # 调用 commands.py 中的实现，并代理 yield
        async for result in commands.list_collections_cmd_impl(self, event):
            yield result
        return

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("drop_collection")  # type: ignore
    async def delete_collection_cmd(
        self,
        event: AstrMessageEvent,
        collection_name: str,
        confirm: Optional[str] = None,
    ):
        """[管理员] 删除指定的 Milvus 集合及其所有数据
        使用示例：/memory drop_collection [collection_name] [confirm]
        """
        async for result in commands.delete_collection_cmd_impl(
            self, event, collection_name, confirm
        ):
            yield result

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("list_records")  # type: ignore
    async def list_records_cmd(
        self,
        event: AstrMessageEvent,
        collection_name: Optional[str] = None,
        limit: int = 5
    ):
        """查询指定集合的记忆记录 (按创建时间倒序显示)
        使用示例: /memory list_records [collection_name] [limit]
        """
        async for result in commands.list_records_cmd_impl(
            self, event, collection_name, limit
        ):
            yield result
        return

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("delete_session_memory")  # type: ignore
    async def delete_session_memory_cmd(
        self, event: AstrMessageEvent, session_id: str, confirm: Optional[str] = None
    ):
        """[管理员] 删除指定会话 ID 相关的所有记忆信息
        使用示例：/memory delete_session_memory [session_id] [confirm]
        """
        async for result in commands.delete_session_memory_cmd_impl(
            self, event, session_id, confirm
        ):
            yield result
        return

    @permission_type(PermissionType.MEMBER)
    @memory_group.command("reset")
    async def reset_session_memory_cmd(self, event: AstrMessageEvent, confirm: Optional[str] = None):
        """清除当前会话 ID 的记忆信息
        使用示例：/memory reset [confirm]
        """
        if not self.context._config.get("platform_settings").get("unique_session") :
            if is_group_chat(event):
                yield event.plain_result("⚠️ 未开启群聊会话隔离，禁止清除群聊长期记忆")
                return
        session_id = await self.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        async for result in commands.delete_session_memory_cmd_impl(
                self, event, session_id, confirm
        ):
            yield result
        return


    @memory_group.command("get_session_id")  # type: ignore
    async def get_session_id_cmd(self, event: AstrMessageEvent):
        """获取当前与您对话的会话 ID
        使用示例：/memory get_session_id
        """
        async for result in commands.get_session_id_cmd_impl(self, event):
            yield result
        return

    # --- 插件生命周期方法 ---
    async def terminate(self):
        """插件停止时的清理逻辑"""
        self.logger.info("Mnemosyne 插件正在停止...")
        # --- 停止后台总结检查任务 ---
        if self._summary_check_task and not self._summary_check_task.done():
            self.logger.info("正在取消后台总结检查任务...")
            self._summary_check_task.cancel()  # <--- 取消任务
            try:
                # 等待任务实际取消完成，设置一个超时避免卡住
                await asyncio.wait_for(self._summary_check_task, timeout=5.0)
            except asyncio.CancelledError:
                self.logger.info("后台总结检查任务已成功取消。")
            except asyncio.TimeoutError:
                self.logger.warning("等待后台总结检查任务取消超时。")
            except Exception as e:
                # 捕获可能在任务取消过程中抛出的其他异常
                self.logger.error(f"等待后台任务取消时发生错误: {e}", exc_info=True)
        self._summary_check_task = None  # 清理任务引用

        if self.milvus_manager and self.milvus_manager.is_connected():
            try:
                if (
                    not self.milvus_manager._is_lite
                    and self.milvus_manager.has_collection(self.collection_name)
                ):
                    self.logger.info(
                        f"正在从内存中释放集合 '{self.collection_name}'..."
                    )
                    self.milvus_manager.release_collection(self.collection_name)

                self.logger.info("正在断开与 Milvus 的连接...")
                self.milvus_manager.disconnect()
                self.logger.info("Milvus 连接已成功断开。")

            except Exception as e:
                self.logger.error(f"停止插件时与 Milvus 交互出错: {e}", exc_info=True)
        else:
            self.logger.info("Milvus 管理器未初始化或已断开连接，无需断开。")
        self.logger.info("Mnemosyne 插件已停止。")
        return
