# -*- coding: utf-8 -*-
"""
Mnemosyne - 基于 RAG 的 AstrBot 长期记忆插件主文件
负责插件注册、初始化流程调用、事件和命令的绑定。
"""

from typing import List, Optional

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

# --- 类型定义和依赖库 ---
from pymilvus import CollectionSchema
from .memory_manager.message_counter import MessageCounter
from .memory_manager.vector_db.milvus_manager import MilvusManager
from .memory_manager.embedding import OpenAIEmbeddingAPI


@register(
    "Mnemosyne",
    "lxfight",
    "一个AstrBot插件，实现基于RAG技术的长期记忆功能。",
    "0.3.6",
    "https://github.com/lxfight/astrbot_plugin_mnemosyne",
)
class Mnemosyne(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.context = context
        self.logger = LogManager.GetLogger(log_name="Mnemosyne")
        self.logger.info("开始初始化 Mnemosyne 插件...")

        # --- 初始化核心组件状态 ---
        self.collection_schema: Optional[CollectionSchema] = None
        self.index_params: dict = {}
        self.search_params: dict = {}
        self.output_fields_for_query: List[str] = []
        self.collection_name: str = DEFAULT_COLLECTION_NAME
        self.milvus_manager: Optional[MilvusManager] = None
        self.msg_counter: Optional[MessageCounter] = None
        # self.context_manager: Optional[ConversationContextManager] = None
        self.ebd: Optional[OpenAIEmbeddingAPI] = None
        self.provider = None

        # 是否需要刷新
        self.flush_after_insert = False
        # --- 执行初始化流程 ---
        try:
            initialization.initialize_config_check(self)
            initialization.initialize_config_and_schema(self)  # 初始化配置和schema
            initialization.initialize_milvus(self)  # 初始化 Milvus
            initialization.initialize_components(self)  # 初始化核心组件
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
        limit: int = 5,
        offset: int = 0,
    ):
        """查询指定集合的记忆记录 (按创建时间倒序显示)
        使用示例: /memory list_records [collection_name] [limit] [offset]
        """
        async for result in commands.list_records_cmd_impl(
            self, event, collection_name, limit, offset
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
        if self.milvus_manager and self.milvus_manager.is_connected():
            try:
                if self.milvus_manager.has_collection(self.collection_name):
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
