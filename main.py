"""
Mnemosyne - 基于 RAG 的 AstrBot 长期记忆插件主文件
负责插件注册、初始化流程调用、事件和命令的绑定。
"""

import asyncio
import time
from typing import Any, cast

# --- 类型定义和依赖库 ---
from pymilvus import CollectionSchema

from astrbot.api import AstrBotConfig, logger  # 使用统一的 logger 和配置类型

# --- AstrBot 核心导入 ---
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.provider.provider import EmbeddingProvider

from .admin_panel.server import AdminPanelServer

# --- 插件内部模块导入 ---
from .core import (
    commands,  # 导入命令处理实现模块
    initialization,  # 导入初始化逻辑模块
    memory_operations,  # 导入记忆操作逻辑模块
)
from .core.constants import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_SUMMARY_CHECK_INTERVAL_SECONDS,
    DEFAULT_SUMMARY_TIME_THRESHOLD_SECONDS,
)  # 导入使用的常量
from .core.tools import is_group_chat
from .memory_manager.context_manager import ConversationContextManager
from .memory_manager.message_counter import MessageCounter
from .memory_manager.vector_db.milvus_manager import MilvusManager


@register(
    "Mnemosyne",
    "lxfight",
    "一个AstrBot插件，实现基于RAG技术的长期记忆功能。",
    "2.0.0",
    "https://github.com/lxfight/astrbot_plugin_mnemosyne",
)
class Mnemosyne(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.context = context

        # --- 初始化核心组件状态 ---
        self.collection_schema: CollectionSchema | None = None
        self.index_params: dict = {}
        self.search_params: dict = {}
        self.output_fields_for_query: list[str] = []
        self.collection_name: str = DEFAULT_COLLECTION_NAME
        self.milvus_manager: MilvusManager | None = None
        self.milvus_adapter: Any = None  # MilvusVectorDB 适配器（可选）
        self.msg_counter: MessageCounter | None = None
        self.context_manager: ConversationContextManager | None = None
        self.embedding_provider: EmbeddingProvider | None = None
        self.provider = None
        self.admin_panel_server: AdminPanelServer | None = None  # 管理面板服务器
        self.admin_panel_thread = None  # 管理面板服务器线程

        # --- 初始化状态标记 ---
        self._initialization_successful = False
        self._initialized_components = []
        self._embedding_provider_ready = False

        logger.info("开始初始化 Mnemosyne 插件...")
        # 启动后台异步初始化，但不包括 Embedding Provider 的初始化
        asyncio.create_task(self._initialize_plugin_async())

        # 延迟加载 Embedding Provider，只在需要时才加载
        self._embedding_provider_task = None

    def _initialize_embedding_provider(
        self, silent: bool = False
    ) -> EmbeddingProvider | None:
        """
        获取 Embedding Provider，采用优先级策略：
        1. 从配置指定的 Provider ID 获取
        2. 使用框架默认的第一个 Embedding Provider

        Args:
            silent: 是否静默模式（不输出警告日志）

        返回:
            EmbeddingProvider 实例，如果不可用则返回 None
        """
        try:
            # 优先级 1: 从配置指定的 Provider ID 获取
            emb_id = self.config.get("embedding_provider_id")
            if emb_id:
                provider = self.context.get_provider_by_id(emb_id)
                # 安全地检查 provider 是否为 EmbeddingProvider 类型
                if provider:
                    # 检查 provider 是否具有 EmbeddingProvider 的关键方法
                    if callable(getattr(provider, "embed_texts", None)) or callable(
                        getattr(provider, "get_embedding", None)
                    ):
                        logger.info(f" 成功从配置加载 Embedding Provider: {emb_id}")
                        # 使用类型断言确保返回正确的类型
                        embedding_provider = cast(EmbeddingProvider, provider)
                        return embedding_provider
                    else:
                        if not silent:
                            logger.warning(
                                f"获取的 Provider {emb_id} 不是有效的 EmbeddingProvider 类型"
                            )

            # 优先级 2: 使用框架默认的第一个 Embedding Provider
            # 使用 context 提供的方法获取所有 embedding providers
            embedding_providers = self.context.get_all_embedding_providers()
            if embedding_providers and len(embedding_providers) > 0:
                provider = embedding_providers[0]
                provider_id = getattr(provider, "provider_config", {}).get(
                    "id", "unknown"
                )
                logger.info(f" 未指定 Embedding Provider，使用默认的: {provider_id}")
                embedding_provider = cast(EmbeddingProvider, provider)
                return embedding_provider

            if not silent:
                logger.debug("当前没有可用的 Embedding Provider")
            return None

        except Exception as e:
            if not silent:
                logger.error(f"获取 Embedding Provider 失败: {e}", exc_info=True)
            return None

    async def _initialize_embedding_provider_async(
        self, max_wait: float = 10.0
    ) -> bool:
        """
        非阻塞地初始化 Embedding Provider（静默模式，减少日志噪音）

        Args:
            max_wait: 最大等待时间（秒）

        返回:
            True 如果成功获取，False 如果超时
        """
        start_time = time.time()
        check_interval = 1.0  # 每 1 秒检查一次，减少频率
        attempt = 0
        last_log_time = start_time

        while time.time() - start_time < max_wait:
            # 静默模式尝试获取
            self.embedding_provider = self._initialize_embedding_provider(silent=True)
            attempt += 1

            if self.embedding_provider:
                logger.info(
                    f" Embedding Provider 已就绪 (用时 {time.time() - start_time:.1f}s)"
                )
                self._embedding_provider_ready = True

                # 获取向量维度并更新配置
                try:
                    dim = getattr(self.embedding_provider, "embedding_dim", None)
                    if not dim:
                        # 尝试通过 get_dim 方法获取
                        if callable(getattr(self.embedding_provider, "get_dim", None)):
                            dim = self.embedding_provider.get_dim()

                    if dim:
                        self.config["embedding_dim"] = dim
                        logger.info(f"检测到 embedding 维度: {dim}")
                except Exception as e:
                    logger.debug(f"无法获取 embedding 维度: {e}")

                return True

            # 每5秒输出一次等待日志，避免日志刷屏
            current_time = time.time()
            if current_time - last_log_time >= 5.0:
                logger.debug(
                    f"等待 Embedding Provider 初始化... (已等待 {current_time - start_time:.0f}s)"
                )
                last_log_time = current_time

            if time.time() - start_time < max_wait:
                await asyncio.sleep(check_interval)

        logger.warning(
            f"⚠️ Embedding Provider 未就绪（等待 {max_wait:.0f}s 超时）\n"
            f"   提示: 记忆搜索功能需要 Embedding Provider，请在 AstrBot 中配置并启用一个 Embedding Provider"
        )
        return False

    async def _initialize_plugin_async(self):
        """
        非阻塞的异步初始化流程
        """
        try:
            # 0. 先在主模块中获取数据目录
            plugin_data_dir = None
            try:
                from astrbot.api.star import StarTools

                plugin_data_dir = str(StarTools.get_data_dir())
                logger.info(f"已获取插件数据目录: {plugin_data_dir}")
            except Exception as e:
                logger.warning(f"无法获取插件数据目录: {e}，将使用后备方案")

            # 1. Embedding Provider 采用延迟初始化策略
            # 在后台静默尝试加载，但不阻塞插件启动
            logger.info("Embedding Provider 采用延迟初始化策略")

            # 启动 Embedding Provider 后台加载任务（静默模式）
            self._embedding_provider_task = asyncio.create_task(
                self._initialize_embedding_provider_async(max_wait=10.0)
            )

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
                self.summary_time_threshold = -1  # 使用-1表示禁用，而不是float("inf")
            self.flush_after_insert = False
            self._summary_check_task: asyncio.Task | None = None

            # 初始化其他核心组件（消息计数器、上下文管理器）
            try:
                initialization.initialize_components(self, plugin_data_dir)
                self._initialized_components.append("components")
            except Exception as e:
                logger.warning(f"核心组件初始化失败，将以无记忆总结的模式运行: {e}")
                # 不阻止插件启动，但标记消息计数器为 None 以禁用记忆总结功能
                self.msg_counter = None
                self.context_manager = None

            # Milvus 初始化：失败时不阻止插件启动，允许降级运行
            try:
                initialization.initialize_milvus(self, plugin_data_dir)
                self._initialized_components.append("milvus")
            except Exception as e:
                logger.warning(
                    f"Milvus 初始化失败，插件将以降级模式运行，搜索功能不可用: {e}"
                )
                self.milvus_manager = None

            # 3. 启动后台总结检查任务
            if self.context_manager and self.summary_time_threshold != -1:
                self._summary_check_task = asyncio.create_task(
                    memory_operations._periodic_summarization_check(self)
                )
                self._initialized_components.append("background_task")
                logger.info("后台总结检查任务已启动。")
            elif self.summary_time_threshold == -1:
                logger.info("基于时间的自动总结已禁用，不启动后台检查任务。")
            else:
                logger.warning("Context manager 未初始化，无法启动后台总结检查任务。")

            # 4. 启动 Admin Panel 服务器
            try:
                admin_panel_config = self.config.get("admin_panel", {})
                port = admin_panel_config.get(
                    "port", 8000
                )  # 从配置中获取端口，默认8000
                host = admin_panel_config.get(
                    "host", "127.0.0.1"
                )  # 从配置中获取监听地址，默认127.0.0.1

                # 检查并生成 Admin Panel API 密钥
                api_key = admin_panel_config.get("api_key", "").strip()
                if not api_key:
                    # 生成临时强随机密码（每次重启都会重新生成）
                    import secrets
                    import string

                    # 生成包含大小写字母、数字和特殊字符的48字符强密码
                    alphabet = (
                        string.ascii_letters
                        + string.digits
                        + "!@#$%^&*()-_=+[]{}|;:,.<>?"
                    )
                    api_key = "".join(secrets.choice(alphabet) for _ in range(48))

                    # 注意：不保存到配置文件中，这样每次重启都会生成新密钥
                    logger.warning("Admin Panel API 密钥未配置，已自动生成临时强密码。")
                    logger.critical(
                        f"临时 Admin Panel API 密钥（请妥善保管）: {api_key}"
                    )
                    logger.info(
                        "此密钥仅在本次运行中有效，重启后将生成新密钥，旧密钥将失效。\n"
                        "   如需固定密钥，请在配置文件中手动设置 admin_panel.api_key\n"
                        "   重要提示：每次重启后必须使用新的密钥重新认证"
                    )
                else:
                    logger.info("Admin Panel API 密钥已配置（固定密钥）")

                self.admin_panel_server = AdminPanelServer(
                    self, port=port, host=host, api_key=api_key
                )
                # 在独立线程中启动服务器
                import threading

                if self.admin_panel_server:  # 确保服务器实例已创建
                    self.admin_panel_thread = threading.Thread(
                        target=self.admin_panel_server.run_in_thread, daemon=True
                    )
                    self.admin_panel_thread.start()
                    logger.info(f"✅ Admin Panel 服务器已启动: http://{host}:{port}")
                    if host == "0.0.0.0":
                        logger.warning(
                            "⚠️ Admin Panel 正在监听所有网络接口 (0.0.0.0)，请确保已设置强密码并注意网络安全"
                        )
            except Exception as e:
                logger.warning(f"⚠️ 启动 Admin Panel 服务器失败: {e}")

            # 5. 标记初始化成功
            self._initialization_successful = True
            logger.info(
                f" Mnemosyne 插件初始化成功。"
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
            # 等待 Embedding Provider 加载完成（如果正在加载）
            if (
                self._embedding_provider_task
                and not self._embedding_provider_task.done()
            ):
                logger.debug("等待 Embedding Provider 加载完成...")
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._embedding_provider_task), timeout=5.0
                    )
                    logger.info("Embedding Provider 加载完成")
                except asyncio.TimeoutError:
                    logger.warning("等待 Embedding Provider 加载超时，继续执行...")
                except Exception as e:
                    logger.error(f"加载 Embedding Provider 时发生错误: {e}")

            # 需要时初始化 Embedding Provider（首次使用）
            if not self._embedding_provider_ready and not self.embedding_provider:
                logger.info("首次使用记忆功能，尝试获取 Embedding Provider...")
                self.embedding_provider = self._initialize_embedding_provider(
                    silent=False
                )
                if self.embedding_provider:
                    self._embedding_provider_ready = True
                    # 获取向量维度并更新配置
                    try:
                        dim = getattr(self.embedding_provider, "embedding_dim", None)
                        if not dim and callable(
                            getattr(self.embedding_provider, "get_dim", None)
                        ):
                            dim = self.embedding_provider.get_dim()

                        if dim:
                            self.config["embedding_dim"] = dim
                            logger.info(f"Embedding 维度: {dim}")
                    except Exception as e:
                        logger.debug(f"无法获取 embedding 维度: {e}")
                else:
                    logger.warning(
                        "⚠️ 无法获取 Embedding Provider\n"
                        "   记忆搜索功能将不可用，请在 AstrBot 中配置 Embedding Provider"
                    )

            if not self.provider:
                provider_id = self.config.get("LLM_providers", "")

                # 验证 provider_id 的有效性
                if not provider_id:
                    logger.warning(
                        "LLM_providers 未配置，尝试使用当前正在使用的 provider"
                    )
                    try:
                        # 支持会话隔离：传入umo参数
                        self.provider = self.context.get_using_provider(
                            umo=event.unified_msg_origin
                        )
                        if not self.provider:
                            logger.error("无法获取任何可用的 LLM provider")
                            return
                    except Exception as e:
                        logger.error(f"获取当前使用的 provider 失败: {e}")
                        return
                else:
                    # 验证 provider_id 格式
                    import re

                    if not re.match(r"^[a-zA-Z0-9_-]+$", provider_id):
                        logger.error(f"provider_id 格式无效: {provider_id}")
                        return

                    # 尝试获取指定的 provider
                    try:
                        self.provider = self.context.get_provider_by_id(provider_id)
                        if not self.provider:
                            logger.error(
                                f"无法找到 provider_id '{provider_id}' 对应的 provider"
                            )
                            # 回退到使用当前 provider（支持会话隔离）
                            logger.warning("回退到使用当前正在使用的 provider")
                            self.provider = self.context.get_using_provider(
                                umo=event.unified_msg_origin
                            )
                            if not self.provider:
                                logger.error(
                                    "回退失败，无法获取任何可用的 LLM provider"
                                )
                                return
                    except Exception as e:
                        logger.error(
                            f"获取 provider_id '{provider_id}' 时发生错误: {e}"
                        )
                        return

            await memory_operations.handle_query_memory(self, event, req)
        except Exception as e:
            logger.error(f"处理 on_llm_request 钩子时发生捕获异常: {e}", exc_info=True)
        return

    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        """[事件钩子] 在 LLM 响应后"""
        try:
            result = memory_operations.handle_on_llm_resp(self, event, resp)
            # 检查返回值是否是可等待对象，如果不是则直接返回
            if result and hasattr(result, "__await__"):
                await result
        except Exception as e:
            logger.error(f"处理 on_llm_response 钩子时发生捕获异常: {e}", exc_info=True)
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
        confirm: str | None = None,
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
        collection_name: str | None = None,
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
        self, event: AstrMessageEvent, session_id: str, confirm: str | None = None
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
        self, event: AstrMessageEvent, confirm: str | None = None
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
        if session_id:  # 确保session_id不为None
            async for result in commands.delete_session_memory_cmd_impl(
                self, event, session_id, confirm
            ):
                yield result
        else:
            yield event.plain_result("无法获取当前会话ID")
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
        if (
            hasattr(self, "_summary_check_task")
            and self._summary_check_task
            and not self._summary_check_task.done()
        ):
            self._summary_check_task.cancel()
            logger.debug("已取消后台总结任务")

        # 清理消息计数器
        if hasattr(self, "msg_counter") and self.msg_counter:
            try:
                if hasattr(self.msg_counter, "close"):
                    self.msg_counter.close()
                    logger.debug("已关闭消息计数器连接")
            except Exception as e:
                logger.error(f"清理消息计数器时出错: {e}")

        # 清理 Milvus 连接
        if hasattr(self, "milvus_manager") and self.milvus_manager:
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

        # --- 停止 Admin Panel 服务器 ---
        if self.admin_panel_server:
            try:
                await self.admin_panel_server.stop()
                logger.info("Admin Panel 服务器已停止。")
            except Exception as e:
                logger.error(f"停止 Admin Panel 服务器时出错: {e}", exc_info=True)

        # S0 优化: 清理消息计数器数据库连接
        if self.msg_counter:
            try:
                if hasattr(self.msg_counter, "close"):
                    self.msg_counter.close()
                    logger.info("消息计数器数据库连接已关闭。")
            except Exception as e:
                logger.error(f"关闭消息计数器时出错: {e}", exc_info=True)

        # 清理 Milvus 连接
        if self.milvus_manager and self.milvus_manager.is_connected():
            try:
                # 不再释放集合，避免下次启动时重新加载导致启动过慢
                # Milvus Lite 不需要手动管理内存，独立部署的 Milvus 由其自己负责
                # if (
                #     not self.milvus_manager._is_lite
                #     and self.milvus_manager.has_collection(self.collection_name)
                # ):
                #     logger.info(f"正在从内存中释放集合 '{self.collection_name}'...")
                #     self.milvus_manager.release_collection(self.collection_name)

                logger.info("正在断开与 Milvus 的连接...")
                self.milvus_manager.disconnect()
                logger.info("Milvus 连接已成功断开。")

            except Exception as e:
                logger.error(f"停止插件时与 Milvus 交互出错: {e}", exc_info=True)
        else:
            logger.info("Milvus 管理器未初始化或已断开连接，无需断开。")

        logger.info("Mnemosyne 插件已完全停止，所有资源已释放。")
        return
