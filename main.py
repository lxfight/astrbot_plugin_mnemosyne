# -*- coding: utf-8 -*-
"""
Mnemosyne - 基于 RAG 的 AstrBot 长期记忆插件主文件
负责插件注册、初始化流程调用、事件和命令的绑定。
"""

import asyncio
from typing import List, Optional, Union
import time


# --- AstrBot 核心导入 ---
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig  # 使用统一的 logger 和配置类型
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.provider.provider import EmbeddingProvider

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
from .memory_manager.context_manager import ConversationContextManager
import time


@register(
    "Mnemosyne",
    "lxfight",
    "一个AstrBot插件，实现基于RAG技术的长期记忆功能。",
    "0.5.2",
    "https://github.com/lxfight/astrbot_plugin_mnemosyne",
)
class Mnemosyne(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.context = context

        # --- 初始化核心组件状态 ---
        self.collection_schema: Optional[CollectionSchema] = None
        self.index_params: dict = {}
        self.search_params: dict = {}
        self.output_fields_for_query: List[str] = []
        self.collection_name: str = DEFAULT_COLLECTION_NAME
        self.milvus_manager: Optional[MilvusManager] = None
        self.msg_counter: Optional[MessageCounter] = None
        self.context_manager: Optional[ConversationContextManager] = None
        self.embedding_provider: Optional[EmbeddingProvider] = None
        self.provider = None

        # --- 初始化状态标记 ---
        self._initialization_successful = False
        self._initialized_components = []
        self._embedding_provider_ready = False

        logger.info("开始初始化 Mnemosyne 插件...")
        # 启动后台异步初始化
        asyncio.create_task(self._initialize_plugin_async())

    def _initialize_embedding_provider(self) -> Optional[EmbeddingProvider]:
        """
        获取 Embedding Provider，采用优先级策略：
        1. 从配置指定的 Provider ID 获取
        2. 使用框架默认的第一个 Embedding Provider

        返回:
            EmbeddingProvider 实例，如果不可用则返回 None
        """
        try:
            # 优先级 1: 从配置指定的 Provider ID 获取
            emb_id = self.config.get("embedding_provider_id")
            if emb_id:
                provider = self.context.get_provider_by_id(emb_id)
                if provider and hasattr(provider, 'embed'):
                    logger.info(f"成功从配置加载 Embedding Provider: {emb_id}")
                    return provider

            # 优先级 2: 使用框架默认的第一个 Embedding Provider
            embedding_providers = self.context.provider_manager.embedding_provider_insts
            if embedding_providers:
                provider = embedding_providers[0]
                logger.info(
                    f"未指定 Embedding Provider，使用默认的: "
                    f"{provider.provider_config.get('id')}"
                )
                return provider

            logger.warning("没有可用的 Embedding Provider")
            return None

        except Exception as e:
            logger.error(f"获取 Embedding Provider 失败: {e}", exc_info=True)
            return None

    async def _initialize_embedding_provider_async(self, max_wait: float = 10.0) -> bool:
        """
        非阻塞地初始化 Embedding Provider

        Args:
            max_wait: 最大等待时间（秒）

        返回:
            True 如果成功获取，False 如果超时
        """
        start_time = time.time()
        check_interval = 0.5  # 每 0.5 秒检查一次
        attempt = 0

        while time.time() - start_time < max_wait:
            self.embedding_provider = self._initialize_embedding_provider()
            attempt += 1

            if self.embedding_provider:
                logger.info(
                    f"✅ Embedding Provider 在第 {attempt} 次尝试后就绪 "
                    f"(用时 {time.time() - start_time:.1f}s)"
                )
                self._embedding_provider_ready = True

                # 获取向量维度并更新配置
                try:
                    dim = self.embedding_provider.embedding_dim
                    if dim:
                        self.config["embedding_dim"] = dim
                        logger.info(f"检测到 embedding 维度: {dim}")
                except Exception as e:
                    logger.debug(f"无法获取 embedding 维度: {e}")

                return True

            if time.time() - start_time < max_wait:
                await asyncio.sleep(check_interval)

        logger.warning(
            f"❌ 在 {max_wait}s 内未能获取 Embedding Provider "
            f"(已尝试 {attempt} 次)"
        )
        return False

    async def _initialize_plugin_async(self):
        """
        非阻塞的异步初始化流程
        """
        try:
            # 1. 非阻塞初始化 Embedding Provider
            embedding_ready = await self._initialize_embedding_provider_async(max_wait=10.0)

            if not embedding_ready:
                logger.warning(
                    "⚠️ Embedding Provider 未就绪，将以降级模式运行。"
                    "搜索功能可能受限。"
                )
                # 不返回，继续初始化其他组件

            # 2. 继续初始化其他组件
            try:
                initialization.initialize_config_check(self)
                self._initialized_components.append("config_check")
            except Exception as e:
                logger.error(f"配置检查失败: {e}", exc_info=True)
                raise

            try:
                initialization.initialize_config_and_schema(self)
                self._initialized_components.append("config_schema")
            except Exception as e:
                logger.error(f"Schema 初始化失败: {e}", exc_info=True)
                raise

            # --- 初始化摘要检查配置 ---
            summary_check_config = self.config.get("summary_check_task", {})
            self.summary_check_interval: int = summary_check_config.get(
                "SUMMARY_CHECK_INTERVAL_SECONDS", DEFAULT_SUMMARY_CHECK_INTERVAL_SECONDS
            )
            self.summary_time_threshold: int = summary_check_config.get(
                "SUMMARY_TIME_THRESHOLD_SECONDS", DEFAULT_SUMMARY_TIME_THRESHOLD_SECONDS
            )
            if self.summary_time_threshold <= 0:
                logger.warning(
                    f"配置的 SUMMARY_TIME_THRESHOLD_SECONDS ({self.summary_time_threshold}) 无效，将禁用基于时间的自动总结。"
                )
                self.summary_time_threshold = float("inf")
            self.flush_after_insert = False
            self._summary_check_task: Optional[asyncio.Task] = None

            # 初始化其他核心组件（消息计数器、上下文管理器）
            try:
                initialization.initialize_components(self)
                self._initialized_components.append("components")
            except Exception as e:
                logger.warning(
                    f"核心组件初始化失败，将以无记忆总结的模式运行: {e}"
                )
                # 不阻止插件启动，但标记消息计数器为 None 以禁用记忆总结功能
                self.msg_counter = None
                self.context_manager = None

            # Milvus 初始化：失败时不阻止插件启动，允许降级运行
            try:
                initialization.initialize_milvus(self)
                self._initialized_components.append("milvus")
            except Exception as e:
                logger.warning(
                    f"Milvus 初始化失败，插件将以降级模式运行，搜索功能不可用: {e}"
                )
                self.milvus_manager = None

            # 3. 启动后台总结检查任务
            if self.context_manager and self.summary_time_threshold != float("inf"):
                self._summary_check_task = asyncio.create_task(
                    memory_operations._periodic_summarization_check(self)
                )
                self._initialized_components.append("background_task")
                logger.info("后台总结检查任务已启动。")
            elif self.summary_time_threshold == float("inf"):
                logger.info("基于时间的自动总结已禁用，不启动后台检查任务。")
            else:
                logger.warning(
                    "Context manager 未初始化，无法启动后台总结检查任务。"
                )

            # 4. 标记初始化成功
            self._initialization_successful = True
            logger.info(
                f"✅ Mnemosyne 插件初始化成功。"
                f"已初始化组件: {', '.join(self._initialized_components)}"
            )

        except Exception as e:
            logger.critical(
                f"❌ Mnemosyne 插件初始化失败: {e}。"
                f"已初始化的组件: {', '.join(self._initialized_components)}",
                exc_info=True,
            )
            self._cleanup_partial_initialization()
            raise

    # --- 事件处理钩子 (调用 memory_operations.py 中的实现) ---
    @filter.on_llm_request()
    async def query_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """[事件钩子] 在 LLM 请求前，查询并注入长期记忆。"""
        # 当会话第一次发生时，插件会从AstrBot中获取上下文历史，之后的会话历史由插件自动管理
        try:
            if not self.provider:
                provider_id = self.config.get("LLM_providers", "")

                # 验证 provider_id 的有效性
                if not provider_id:
                    logger.warning("LLM_providers 未配置，尝试使用当前正在使用的 provider")
                    try:
                        # 支持会话隔离：传入umo参数
                        self.provider = self.context.get_using_provider(umo=event.unified_msg_origin)
                        if not self.provider:
                            logger.error("无法获取任何可用的 LLM provider")
                            return
                    except Exception as e:
                        logger.error(f"获取当前使用的 provider 失败: {e}")
                        return
                else:
                    # 验证 provider_id 格式
                    import re
                    if not re.match(r'^[a-zA-Z0-9_-]+$', provider_id):
                        logger.error(f"provider_id 格式无效: {provider_id}")
                        return

                    # 尝试获取指定的 provider
                    try:
                        self.provider = self.context.get_provider_by_id(provider_id)
                        if not self.provider:
                            logger.error(f"无法找到 provider_id '{provider_id}' 对应的 provider")
                            # 回退到使用当前 provider（支持会话隔离）
                            logger.warning("回退到使用当前正在使用的 provider")
                            self.provider = self.context.get_using_provider(umo=event.unified_msg_origin)
                            if not self.provider:
                                logger.error("回退失败，无法获取任何可用的 LLM provider")
                                return
                    except Exception as e:
                        logger.error(f"获取 provider_id '{provider_id}' 时发生错误: {e}")
                        return

            await memory_operations.handle_query_memory(self, event, req)
        except Exception as e:
            logger.error(
                f"处理 on_llm_request 钩子时发生捕获异常: {e}", exc_info=True
            )
        return

    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        """[事件钩子] 在 LLM 响应后"""
        try:
            await memory_operations.handle_on_llm_resp(self, event, resp)
        except Exception as e:
            logger.error(
                f"处理 on_llm_response 钩子时发生捕获异常: {e}", exc_info=True
            )
        return

    # --- 命令处理 (定义方法并应用装饰器，调用 commands.py 中的实现) ---

    @filter.command_group("memory")
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

    @filter.permission_type(filter.PermissionType.ADMIN)
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

    @filter.permission_type(filter.PermissionType.ADMIN)
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

    @filter.permission_type(filter.PermissionType.ADMIN)
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

    @filter.permission_type(filter.PermissionType.MEMBER)
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
        logger.warning("开始清理部分初始化的资源...")
        
        # 清理后台任务
        if hasattr(self, '_summary_check_task') and self._summary_check_task and not self._summary_check_task.done():
            self._summary_check_task.cancel()
            logger.debug("已取消后台总结任务")
        
        # 清理消息计数器
        if hasattr(self, 'msg_counter') and self.msg_counter:
            try:
                if hasattr(self.msg_counter, 'close'):
                    self.msg_counter.close()
                    logger.debug("已关闭消息计数器连接")
            except Exception as e:
                logger.error(f"清理消息计数器时出错: {e}")
        
        # 清理 Milvus 连接
        if hasattr(self, 'milvus_manager') and self.milvus_manager:
            try:
                if self.milvus_manager.is_connected():
                    self.milvus_manager.disconnect()
                    logger.debug("已断开 Milvus 连接")
            except Exception as e:
                logger.error(f"清理 Milvus 连接时出错: {e}")
        
        logger.info("资源清理完成")
    
    async def terminate(self):
        """
        S0 优化: 增强的插件停止清理逻辑
        确保所有资源正确释放
        """
        logger.info("Mnemosyne 插件正在停止...")
        
        # --- 停止后台总结检查任务 ---
        if self._summary_check_task and not self._summary_check_task.done():
            logger.info("正在取消后台总结检查任务...")
            self._summary_check_task.cancel()
            try:
                # 等待任务实际取消完成，设置一个超时避免卡住
                await asyncio.wait_for(self._summary_check_task, timeout=5.0)
            except asyncio.CancelledError:
                logger.info("后台总结检查任务已成功取消。")
            except asyncio.TimeoutError:
                logger.warning("等待后台总结检查任务取消超时。")
            except Exception as e:
                logger.error(f"等待后台任务取消时发生错误: {e}", exc_info=True)
        self._summary_check_task = None

        # S0 优化: 清理消息计数器数据库连接
        if self.msg_counter:
            try:
                if hasattr(self.msg_counter, 'close'):
                    self.msg_counter.close()
                    logger.info("消息计数器数据库连接已关闭。")
            except Exception as e:
                logger.error(f"关闭消息计数器时出错: {e}", exc_info=True)

        # 清理 Milvus 连接
        if self.milvus_manager and self.milvus_manager.is_connected():
            try:
                if (
                    not self.milvus_manager._is_lite
                    and self.milvus_manager.has_collection(self.collection_name)
                ):
                    logger.info(
                        f"正在从内存中释放集合 '{self.collection_name}'..."
                    )
                    self.milvus_manager.release_collection(self.collection_name)

                logger.info("正在断开与 Milvus 的连接...")
                self.milvus_manager.disconnect()
                logger.info("Milvus 连接已成功断开。")

            except Exception as e:
                logger.error(f"停止插件时与 Milvus 交互出错: {e}", exc_info=True)
        else:
            logger.info("Milvus 管理器未初始化或已断开连接，无需断开。")
        
        logger.info("Mnemosyne 插件已完全停止，所有资源已释放。")
        return
