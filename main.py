# -*- coding: utf-8 -*-
"""
Mnemosyne - 基于 RAG 的 AstrBot 长期记忆插件主文件
负责插件注册、初始化流程调用、事件和命令的绑定。
"""

import asyncio
from typing import List, Optional, Union
import re


# --- AstrBot 核心导入 ---
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import (
    on_llm_request,
    on_llm_response,
    command_group,
    permission_type,
    PermissionType,
)
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import PlainResult  # 导入消息组件
from astrbot.core.log import LogManager
from astrbot.api.provider import LLMResponse, ProviderRequest

# --- 插件内部模块导入 ---
from .core import initialization  # 导入初始化逻辑模块
from .core import memory_operations  # 导入记忆操作逻辑模块
from .core import commands  # 导入命令处理实现模块
from .core.constants import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_SUMMARY_CHECK_INTERVAL_SECONDS,
    DEFAULT_SUMMARY_TIME_THRESHOLD_SECONDS
)  # 导入使用的常量
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
    "0.5.1",
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
        self.ebd: Optional[Union[OpenAIEmbeddingAPI, GeminiEmbeddingAPI, Star]] = None
        self.provider = None

        # 初始化嵌入服务
        try:
            embedding_plugin = self.context.get_registered_star(
                "astrbot_plugin_embedding_adapter"
            )
            # 安全访问embedding_adapter：检查激活状态和star_cls是否存在
            if (embedding_plugin
                and embedding_plugin.activated
                and embedding_plugin.star_cls is not None):
                self.ebd = embedding_plugin.star_cls
                dim = self.ebd.get_dim()
                model_name = self.ebd.get_model_name()
                if dim is not None and model_name is not None:
                    self.config["embedding_dim"] = dim
                    self.config["collection_name"] = "ea_" + re.sub(
                        r"[^a-zA-Z0-9]", "_", model_name
                    )
            else:
                raise ValueError(
                    "嵌入服务适配器未正确注册、激活或未返回有效的维度和模型名称。"
                )
        except Exception as e:
            self.logger.warning(f"嵌入服务适配器插件加载失败: {e}", exc_info=True)
            self.ebd = None

        if self.ebd is None:
            try:
                embedding_service = config.get("embedding_service", "openai").lower()
                embedding_key = config.get("embedding_key")
                
                # 安全检查：避免记录敏感信息
                if not embedding_key:
                    self.logger.warning("未配置 embedding_key，嵌入服务可能无法正常工作")
                
                if embedding_service == "gemini":
                    self.ebd = GeminiEmbeddingAPI(
                        model=config.get("embedding_model", "gemini-embedding-exp-03-07"),
                        api_key=embedding_key,
                    )
                    self.logger.info("已选择 Gemini 作为嵌入服务提供商")
                else:
                    self.ebd = OpenAIEmbeddingAPI(
                        model=config.get("embedding_model", "text-embedding-3-small"),
                        api_key=embedding_key,
                        base_url=config.get("embedding_url"),
                    )
                    self.logger.info("已选择 OpenAI 作为嵌入服务提供商")
            except Exception as e:
                self.logger.error(
                    f"初始化嵌入服务失败: {e}. 请检查配置或嵌入服务插件是否正确安装。",
                    exc_info=True,
                )
                self.ebd = None

        # --- 消息计时器 ---
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

        # S0 优化: 初始化状态跟踪
        self._initialization_successful = False
        self._initialized_components = []
        
        self.logger.info("开始初始化 Mnemosyne 插件...")
        try:
            # S0 优化: 扁平化异常处理，原子性初始化
            initialization.initialize_config_check(self)
            self._initialized_components.append("config_check")
            
            initialization.initialize_config_and_schema(self)
            self._initialized_components.append("config_schema")
            
            initialization.initialize_milvus(self)
            self._initialized_components.append("milvus")
            
            initialization.initialize_components(self)
            self._initialized_components.append("components")
            
            # --- 启动后台总结检查任务 ---
            if self.context_manager and self.summary_time_threshold != float("inf"):
                # 确保 context_manager 已初始化且阈值有效
                self._summary_check_task = asyncio.create_task(
                    memory_operations._periodic_summarization_check(self)
                )
                self._initialized_components.append("background_task")
                self.logger.info("后台总结检查任务已启动。")
            elif self.summary_time_threshold == float("inf"):
                self.logger.info("基于时间的自动总结已禁用，不启动后台检查任务。")
            else:
                self.logger.warning(
                    "Context manager 未初始化，无法启动后台总结检查任务。"
                )

            # S0 优化: 标记初始化成功
            self._initialization_successful = True
            self.logger.info(f"Mnemosyne 插件初始化成功。已初始化组件: {', '.join(self._initialized_components)}")
            
        except Exception as e:
            # S0 优化: 初始化失败时进行资源清理
            self.logger.critical(
                f"Mnemosyne 插件初始化失败: {e}。已初始化的组件: {', '.join(self._initialized_components)}",
                exc_info=True,
            )
            self._cleanup_partial_initialization()
            raise  # 重新抛出异常，让上层知道初始化失败

    # --- 事件处理钩子 (调用 memory_operations.py 中的实现) ---
    @on_llm_request()
    async def query_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """[事件钩子] 在 LLM 请求前，查询并注入长期记忆。"""
        # 当会话第一次发生时，插件会从AstrBot中获取上下文历史，之后的会话历史由插件自动管理
        try:
            if not self.provider:
                provider_id = self.config.get("LLM_providers", "")

                # 验证 provider_id 的有效性
                if not provider_id:
                    self.logger.warning("LLM_providers 未配置，尝试使用当前正在使用的 provider")
                    try:
                        # 支持会话隔离：传入umo参数
                        self.provider = self.context.get_using_provider(umo=event.unified_msg_origin)
                        if not self.provider:
                            self.logger.error("无法获取任何可用的 LLM provider")
                            return
                    except Exception as e:
                        self.logger.error(f"获取当前使用的 provider 失败: {e}")
                        return
                else:
                    # 验证 provider_id 格式
                    import re
                    if not re.match(r'^[a-zA-Z0-9_-]+$', provider_id):
                        self.logger.error(f"provider_id 格式无效: {provider_id}")
                        return

                    # 尝试获取指定的 provider
                    try:
                        self.provider = self.context.get_provider_by_id(provider_id)
                        if not self.provider:
                            self.logger.error(f"无法找到 provider_id '{provider_id}' 对应的 provider")
                            # 回退到使用当前 provider（支持会话隔离）
                            self.logger.warning("回退到使用当前正在使用的 provider")
                            self.provider = self.context.get_using_provider(umo=event.unified_msg_origin)
                            if not self.provider:
                                self.logger.error("回退失败，无法获取任何可用的 LLM provider")
                                return
                    except Exception as e:
                        self.logger.error(f"获取 provider_id '{provider_id}' 时发生错误: {e}")
                        return

            await memory_operations.handle_query_memory(self, event, req)
        except Exception as e:
            self.logger.error(
                f"处理 on_llm_request 钩子时发生捕获异常: {e}", exc_info=True
            )
        return

    @on_llm_response()
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
        # 使用get_config()而不是直接访问私有属性_config
        config = self.context.get_config()
        if not config.get("platform_settings", {}).get("unique_session"):
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
    def _cleanup_partial_initialization(self):
        """
        S0 优化: 清理部分初始化的资源
        在初始化失败时调用，确保已分配的资源被正确释放
        """
        self.logger.warning("开始清理部分初始化的资源...")
        
        # 清理后台任务
        if hasattr(self, '_summary_check_task') and self._summary_check_task and not self._summary_check_task.done():
            self._summary_check_task.cancel()
            self.logger.debug("已取消后台总结任务")
        
        # 清理消息计数器
        if hasattr(self, 'msg_counter') and self.msg_counter:
            try:
                if hasattr(self.msg_counter, 'close'):
                    self.msg_counter.close()
                    self.logger.debug("已关闭消息计数器连接")
            except Exception as e:
                self.logger.error(f"清理消息计数器时出错: {e}")
        
        # 清理 Milvus 连接
        if hasattr(self, 'milvus_manager') and self.milvus_manager:
            try:
                if self.milvus_manager.is_connected():
                    self.milvus_manager.disconnect()
                    self.logger.debug("已断开 Milvus 连接")
            except Exception as e:
                self.logger.error(f"清理 Milvus 连接时出错: {e}")
        
        self.logger.info("资源清理完成")
    
    async def terminate(self):
        """
        S0 优化: 增强的插件停止清理逻辑
        确保所有资源正确释放
        """
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
                self.logger.error(f"等待后台任务取消时发生错误: {e}", exc_info=True)
        self._summary_check_task = None

        # S0 优化: 清理消息计数器数据库连接
        if self.msg_counter:
            try:
                if hasattr(self.msg_counter, 'close'):
                    self.msg_counter.close()
                    self.logger.info("消息计数器数据库连接已关闭。")
            except Exception as e:
                self.logger.error(f"关闭消息计数器时出错: {e}", exc_info=True)

        # 清理 Milvus 连接
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
        
        self.logger.info("Mnemosyne 插件已完全停止，所有资源已释放。")
        return
