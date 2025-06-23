# -*- coding: utf-8 -*-
"""
Mnemosyne - 基于 RAG 的 AstrBot 长期记忆插件主文件
负责插件注册、初始化流程调用、事件和命令的绑定。

支持多种向量数据库后端：Milvus 和 FAISS
支持 AstrBot 原生嵌入服务和传统实现
"""

import asyncio
from typing import List, Optional
import re


# --- AstrBot 核心导入 ---
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import PermissionType, permission_type
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *  # 导入 AstrBot API
from astrbot.api.message_components import *  # 导入消息组件
from astrbot.core.log import LogManager
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import StarTools

# --- 插件内部模块导入 ---
from .core import initialization  # 导入初始化逻辑模块
from .core import memory_operations  # 导入记忆操作逻辑模块
from .core import commands  # 导入命令处理实现模块
from .core.constants import *  # 导入所有常量
from .core.tools import is_group_chat

# --- 现代化的依赖库 ---
from .memory_manager.message_counter import MessageCounter
from .memory_manager.vector_db import VectorDatabase, VectorDatabaseFactory
from .memory_manager.embedding_adapter import (
    EmbeddingServiceAdapter,
    EmbeddingServiceFactory,
)
from .memory_manager.context_manager import ConversationContextManager


@register(
    "astrbot_plugin_mnemosyne",
    "lxfight",
    "一个AstrBot插件，实现基于RAG技术的长期记忆功能。支持 Milvus 和 FAISS 向量数据库。",
    "0.6.0",
    "https://github.com/lxfight/astrbot_plugin_mnemosyne",
)
class Mnemosyne(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.context = context
        self.logger = LogManager.GetLogger(log_name="Mnemosyne")
        self.plugin_data_path = StarTools.get_data_dir("astrbot_plugin_mnemosyne")

        # --- 初始化核心组件状态 ---
        self.collection_schema: Optional[dict] = None  # 通用 schema 格式
        self.index_params: dict = {}
        self.search_params: dict = {}
        self.output_fields_for_query: List[str] = []
        self.collection_name: str = DEFAULT_COLLECTION_NAME

        # 现代化的组件
        self.vector_db: Optional[VectorDatabase] = None  # 统一的向量数据库接口
        self.embedding_adapter: Optional[EmbeddingServiceAdapter] = (
            None  # 统一的嵌入服务接口
        )
        self.msg_counter: Optional[MessageCounter] = None
        self.context_manager: Optional[ConversationContextManager] = None
        self.provider = None

        # 初始化状态标志
        self.embedding_adapter = None
        self._embedding_init_attempted = False
        self._core_components_initialized = False

        self.logger.info("插件基础组件初始化完成，等待 AstrBot 加载完成后进行完整初始化...")

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

        self.logger.info("Mnemosyne 插件基础初始化完成，等待 AstrBot 加载完成...")

    def _initialize_vector_database(self):
        """初始化向量数据库"""
        try:
            # 确定数据库类型
            db_type = self.config.get("vector_database_type", "milvus").lower()

            # 更新配置中的路径，使用插件专属数据目录
            config_with_paths = self._update_config_paths(self.config.copy())

            # 验证配置
            is_valid, error_msg = VectorDatabaseFactory.validate_config(
                db_type, config_with_paths
            )
            if not is_valid:
                raise ValueError(
                    f"Vector database config validation failed: {error_msg}"
                )

            # 创建数据库实例
            self.vector_db = VectorDatabaseFactory.create_database(
                db_type=db_type, config=config_with_paths, logger=self.logger
            )

            if not self.vector_db:
                raise RuntimeError(f"Failed to create {db_type} database instance")

            # 连接到数据库
            if not self.vector_db.connect():
                raise RuntimeError(f"Failed to connect to {db_type} database")

            # 设置集合名称
            self.collection_name = self.config.get(
                "collection_name", DEFAULT_COLLECTION_NAME
            )

            # 创建集合（如果不存在）
            if not self.vector_db.has_collection(self.collection_name):
                schema = self._create_collection_schema()
                if not self.vector_db.create_collection(self.collection_name, schema):
                    raise RuntimeError(
                        f"Failed to create collection '{self.collection_name}'"
                    )
                self.logger.info(f"Created new collection '{self.collection_name}'")
            else:
                self.logger.info(f"Using existing collection '{self.collection_name}'")

            self.logger.info(f"Successfully initialized {db_type} vector database")

        except Exception as e:
            self.logger.error(
                f"Failed to initialize vector database: {e}", exc_info=True
            )
            raise

    def _update_config_paths(self, config: dict) -> dict:
        """更新配置中的路径，使用插件专属数据目录"""
        import os

        # 更新 FAISS 数据路径
        faiss_config = config.get("faiss_config", {})
        if "faiss_data_path" in faiss_config:
            # 如果是相对路径，则基于插件数据目录
            faiss_path = faiss_config["faiss_data_path"]
            if not os.path.isabs(faiss_path):
                if "faiss_config" not in config:
                    config["faiss_config"] = {}
                config["faiss_config"]["faiss_data_path"] = os.path.join(self.plugin_data_path, faiss_path)
        else:
            # 如果没有配置，使用默认路径
            if "faiss_config" not in config:
                config["faiss_config"] = {}
            config["faiss_config"]["faiss_data_path"] = os.path.join(self.plugin_data_path, "faiss_data")

        # 更新 Milvus Lite 路径
        if "milvus_lite_path" in config and config["milvus_lite_path"]:
            milvus_path = config["milvus_lite_path"]
            if not os.path.isabs(milvus_path):
                config["milvus_lite_path"] = os.path.join(self.plugin_data_path, milvus_path)

        self.logger.debug(f"Updated config paths - FAISS: {config.get('faiss_config', {}).get('faiss_data_path')}, Milvus: {config.get('milvus_lite_path')}")
        return config

    def _create_collection_schema(self) -> dict:
        """创建集合 schema"""
        embedding_dim = self.config.get("embedding_dim", DEFAULT_EMBEDDING_DIM)

        # 通用的 schema 格式，兼容不同的数据库后端
        schema = {
            "vector_dim": embedding_dim,
            "fields": [
                {
                    "name": PRIMARY_FIELD_NAME,
                    "type": "int64",
                    "is_primary": True,
                    "auto_id": True,
                    "description": "唯一记忆标识符",
                },
                {
                    "name": "personality_id",
                    "type": "varchar",
                    "max_length": 256,
                    "description": "与记忆关联的角色ID",
                },
                {
                    "name": "session_id",
                    "type": "varchar",
                    "max_length": 72,
                    "description": "会话ID",
                },
                {
                    "name": "content",
                    "type": "varchar",
                    "max_length": 4096,
                    "description": "记忆内容（摘要或片段）",
                },
                {
                    "name": VECTOR_FIELD_NAME,
                    "type": "float_vector",
                    "dim": embedding_dim,
                    "description": "记忆的嵌入向量",
                },
                {
                    "name": "create_time",
                    "type": "int64",
                    "description": "创建记忆时的时间戳（Unix epoch）",
                },
            ],
        }

        self.collection_schema = schema
        return schema

    # --- 事件处理钩子 (调用 memory_operations.py 中的实现) ---
    @filter.on_llm_request()
    async def query_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """[事件钩子] 在 LLM 请求前，查询并注入长期记忆。"""
        # 检查核心组件是否已初始化
        if not self._core_components_initialized:
            self.logger.debug("核心组件未初始化，跳过长期记忆查询")
            return

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
        # 检查核心组件是否已初始化
        if not self._core_components_initialized:
            self.logger.debug("核心组件未初始化，跳过 LLM 响应处理")
            return

        try:
            await memory_operations.handle_on_llm_resp(self, event, resp)
        except Exception as e:
            self.logger.error(
                f"处理 on_llm_response 钩子时发生捕获异常: {e}", exc_info=True
            )
        return

    # --- 命令处理 (定义方法并应用装饰器，调用 commands.py 中的实现) ---

    def _check_initialization(self, event: AstrMessageEvent):
        """检查插件是否已完全初始化"""
        if not self._core_components_initialized:
            return event.plain_result("⚠️ 插件正在初始化中，请稍后再试...")
        return None

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
        # 检查初始化状态
        init_check = self._check_initialization(event)
        if init_check:
            yield init_check
            return

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
    async def reset_session_memory_cmd(
        self, event: AstrMessageEvent, confirm: Optional[str] = None
    ):
        """清除当前会话 ID 的记忆信息
        使用示例：/memory reset [confirm]
        """
        if not self.context._config.get("platform_settings").get("unique_session"):
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

    # === 迁移相关命令 ===

    @memory_group.command("status")  # type: ignore
    async def migration_status_cmd(self, event: AstrMessageEvent):
        """查看当前插件配置和迁移状态
        使用示例：/memory status
        """
        async for result in commands.migration_status_cmd_impl(self, event):
            yield result
        return

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("migrate_config")  # type: ignore
    async def migrate_config_cmd(self, event: AstrMessageEvent):
        """[管理员] 迁移配置到新格式
        使用示例：/memory migrate_config
        """
        async for result in commands.migrate_config_cmd_impl(self, event):
            yield result
        return

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("migrate_to_faiss")  # type: ignore
    async def migrate_to_faiss_cmd(
        self, event: AstrMessageEvent, confirm: Optional[str] = None
    ):
        """[管理员] 迁移数据到 FAISS 数据库
        使用示例：/memory migrate_to_faiss [--confirm]
        """
        async for result in commands.migrate_to_faiss_cmd_impl(self, event, confirm):
            yield result
        return

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("migrate_to_milvus")  # type: ignore
    async def migrate_to_milvus_cmd(
        self, event: AstrMessageEvent, confirm: Optional[str] = None
    ):
        """[管理员] 迁移数据到 Milvus 数据库
        使用示例：/memory migrate_to_milvus [--confirm]
        """
        async for result in commands.migrate_to_milvus_cmd_impl(self, event, confirm):
            yield result
        return

    @memory_group.command("validate_config")  # type: ignore
    async def validate_config_cmd(self, event: AstrMessageEvent):
        """验证当前配置
        使用示例：/memory validate_config
        """
        async for result in commands.validate_config_cmd_impl(self, event):
            yield result
        return

    @memory_group.command("help")  # type: ignore
    async def help_cmd(self, event: AstrMessageEvent):
        """显示详细帮助信息
        使用示例：/memory help
        """
        async for result in commands.help_cmd_impl(self, event):
            yield result
        return

    # --- 插件生命周期方法 ---

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """AstrBot 加载完成后的钩子，进行完整的插件初始化"""
        if self._core_components_initialized:
            self.logger.debug("核心组件已初始化，跳过重复初始化")
            return

        self.logger.info("AstrBot 加载完成，开始初始化 Mnemosyne 插件核心组件...")

        try:
            # 1. 初始化嵌入服务
            await self._initialize_embedding_service()

            # 2. 初始化配置检查
            initialization.initialize_config_check(self)

            # 3. 初始化向量数据库
            self._initialize_vector_database()

            # 4. 初始化其他核心组件
            initialization.initialize_components(self)

            # 5. 启动后台总结检查任务
            await self._start_background_tasks()

            self._core_components_initialized = True
            self.logger.info("Mnemosyne 插件核心组件初始化成功！")

        except Exception as e:
            self.logger.critical(
                f"Mnemosyne 插件初始化过程中发生严重错误: {e}",
                exc_info=True,
            )

    async def _initialize_embedding_service(self):
        """初始化嵌入服务"""
        try:
            self.embedding_adapter = EmbeddingServiceFactory.create_adapter(
                context=self.context, config=self.config, logger=self.logger
            )

            if self.embedding_adapter:
                # 更新配置中的维度信息
                dim = self.embedding_adapter.get_dim()
                model_name = self.embedding_adapter.get_model_name()

                if dim is not None:
                    self.config["embedding_dim"] = dim

                if model_name and model_name != "unknown":
                    # 根据模型名称生成集合名称
                    safe_model_name = re.sub(r"[^a-zA-Z0-9]", "_", model_name)
                    self.config["collection_name"] = f"mnemosyne_{safe_model_name}"

                self.logger.info(
                    f"成功初始化嵌入服务: {self.embedding_adapter.service_name}"
                )
                self._embedding_init_attempted = True
            else:
                self.logger.warning("嵌入服务初始化失败")
                raise ValueError("无法创建嵌入服务适配器")

        except Exception as e:
            self.logger.error(f"初始化嵌入服务失败: {e}", exc_info=True)
            raise

    async def _start_background_tasks(self):
        """启动后台任务"""
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

    async def terminate(self):
        """插件停止时的清理逻辑"""
        self.logger.info("Mnemosyne 插件正在停止...")

        # --- 停止后台总结检查任务 ---
        if self._summary_check_task and not self._summary_check_task.done():
            self.logger.info("正在取消后台总结检查任务...")
            self._summary_check_task.cancel()
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

        # --- 断开向量数据库连接 ---
        if self.vector_db and self.vector_db.is_connected():
            try:
                self.logger.info(
                    f"正在断开与 {self.vector_db.get_database_type().value} 数据库的连接..."
                )
                if self.vector_db.disconnect():
                    self.logger.info("向量数据库连接已成功断开。")
                else:
                    self.logger.warning("向量数据库断开连接时返回失败状态。")
            except Exception as e:
                self.logger.error(f"停止插件时与向量数据库交互出错: {e}", exc_info=True)
        else:
            self.logger.info("向量数据库未初始化或已断开连接，无需断开。")

        self.logger.info("Mnemosyne 插件已停止。")
        return
