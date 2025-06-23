# -*- coding: utf-8 -*-
"""
现代化的嵌入服务适配器
支持 AstrBot 原生 EmbeddingProvider 和自定义实现的统一接口
"""

import asyncio
from typing import List, Optional
from abc import ABC, abstractmethod

from astrbot.core.log import LogManager
from astrbot.core.provider.provider import EmbeddingProvider


class EmbeddingServiceAdapter(ABC):
    """
    嵌入服务适配器基类
    提供统一的嵌入服务接口
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = LogManager.GetLogger(log_name=f"EmbeddingAdapter-{service_name}")

    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """获取单个文本的嵌入向量"""
        pass

    @abstractmethod
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取文本的嵌入向量"""
        pass

    @abstractmethod
    def get_dim(self) -> int:
        """获取向量维度"""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """获取模型名称"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """测试连接是否正常"""
        pass


class AstrBotEmbeddingAdapter(EmbeddingServiceAdapter):
    """
    AstrBot 原生 EmbeddingProvider 适配器
    """

    def __init__(self, provider: EmbeddingProvider):
        super().__init__("AstrBot-Native")
        self.provider = provider
        self.logger.info("Initialized AstrBot native embedding adapter")

    async def get_embedding(self, text: str) -> List[float]:
        """获取单个文本的嵌入向量"""
        try:
            return await self.provider.get_embedding(text)
        except Exception as e:
            self.logger.error(f"Failed to get embedding: {e}", exc_info=True)
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取文本的嵌入向量"""
        try:
            return await self.provider.get_embeddings(texts)
        except Exception as e:
            self.logger.error(f"Failed to get embeddings: {e}", exc_info=True)
            raise

    def get_dim(self) -> int:
        """获取向量维度"""
        return self.provider.get_dim()

    def get_model_name(self) -> str:
        """获取模型名称"""
        if hasattr(self.provider, "model"):
            return self.provider.model
        elif hasattr(self.provider, "provider_config"):
            return self.provider.provider_config.get("embedding_model", "unknown")
        else:
            return "unknown"

    async def test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            test_text = "Hello, world!"
            await self.get_embedding(test_text)
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False


class LegacyEmbeddingAdapter(EmbeddingServiceAdapter):
    """
    传统嵌入服务适配器（兼容旧版本实现）
    """

    def __init__(self, embedding_service, service_name: str):
        super().__init__(f"Legacy-{service_name}")
        self.embedding_service = embedding_service
        self.logger.info(f"Initialized legacy embedding adapter for {service_name}")

    async def get_embedding(self, text: str) -> List[float]:
        """获取单个文本的嵌入向量"""
        try:
            # 检查是否是异步方法
            if asyncio.iscoroutinefunction(self.embedding_service.get_embeddings):
                embeddings = await self.embedding_service.get_embeddings([text])
            else:
                # 在线程池中运行同步方法
                embeddings = await asyncio.get_event_loop().run_in_executor(
                    None, self.embedding_service.get_embeddings, [text]
                )
            return embeddings[0] if embeddings else []
        except Exception as e:
            self.logger.error(f"Failed to get embedding: {e}", exc_info=True)
            raise

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取文本的嵌入向量"""
        try:
            # 检查是否是异步方法
            if asyncio.iscoroutinefunction(self.embedding_service.get_embeddings):
                return await self.embedding_service.get_embeddings(texts)
            else:
                # 在线程池中运行同步方法
                return await asyncio.get_event_loop().run_in_executor(
                    None, self.embedding_service.get_embeddings, texts
                )
        except Exception as e:
            self.logger.error(f"Failed to get embeddings: {e}", exc_info=True)
            raise

    def get_dim(self) -> int:
        """获取向量维度"""
        if hasattr(self.embedding_service, "get_dim"):
            return self.embedding_service.get_dim()
        elif hasattr(self.embedding_service, "dimension"):
            return self.embedding_service.dimension
        else:
            # 默认维度
            return 1024

    def get_model_name(self) -> str:
        """获取模型名称"""
        if hasattr(self.embedding_service, "model"):
            return self.embedding_service.model
        elif hasattr(self.embedding_service, "get_model_name"):
            return self.embedding_service.get_model_name()
        else:
            return "unknown"

    async def test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            if hasattr(self.embedding_service, "test_connection"):
                # 检查是否是异步方法
                if asyncio.iscoroutinefunction(self.embedding_service.test_connection):
                    return await self.embedding_service.test_connection()
                else:
                    return await asyncio.get_event_loop().run_in_executor(
                        None, self.embedding_service.test_connection
                    )
            else:
                # 通过实际调用来测试
                test_text = "Hello, world!"
                await self.get_embedding(test_text)
                return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False


class EmbeddingServiceFactory:
    """
    嵌入服务工厂类
    负责创建合适的嵌入服务适配器
    """

    @staticmethod
    def create_adapter(
        context, config: dict, logger: Optional[LogManager] = None
    ) -> Optional[EmbeddingServiceAdapter]:
        """
        创建嵌入服务适配器

        Args:
            context: AstrBot 上下文
            config: 插件配置
            logger: 日志记录器

        Returns:
            EmbeddingServiceAdapter 实例或 None
        """
        if logger is None:
            logger = LogManager.GetLogger(log_name="EmbeddingServiceFactory")

        try:
            # 1. 优先尝试使用 AstrBot 原生 EmbeddingProvider
            native_adapter = EmbeddingServiceFactory._try_native_provider(
                context, config, logger
            )
            if native_adapter:
                return native_adapter

            # 2. 回退到传统实现
            legacy_adapter = EmbeddingServiceFactory._try_legacy_provider(
                config, logger
            )
            if legacy_adapter:
                return legacy_adapter

            logger.error("Failed to create any embedding service adapter")
            return None

        except Exception as e:
            logger.error(
                f"Failed to create embedding service adapter: {e}", exc_info=True
            )
            return None

    @staticmethod
    def _try_native_provider(
        context, config: dict, logger
    ) -> Optional[AstrBotEmbeddingAdapter]:
        """尝试使用 AstrBot 原生 EmbeddingProvider"""
        try:
            # 检查是否有可用的 embedding provider
            if not hasattr(context, "provider_manager") or not context.provider_manager:
                logger.debug("No provider manager available")
                return None

            # 尝试根据配置选择特定的 provider
            preferred_provider_id = config.get("embedding_provider_id")
            if preferred_provider_id:
                # 尝试通过 inst_map 获取指定的提供商
                if hasattr(context.provider_manager, "inst_map"):
                    provider = context.provider_manager.inst_map.get(preferred_provider_id)
                    if provider and hasattr(provider, "get_embedding"):
                        logger.info(
                            f"Using preferred embedding provider: {preferred_provider_id}"
                        )
                        return AstrBotEmbeddingAdapter(provider)

            # 尝试获取所有可用的嵌入服务提供商
            embedding_providers = []

            # 方法1：通过 embedding_provider_insts 属性
            if hasattr(context.provider_manager, "embedding_provider_insts"):
                embedding_providers = context.provider_manager.embedding_provider_insts

            # 方法2：通过 inst_map 查找嵌入服务
            elif hasattr(context.provider_manager, "inst_map"):
                for provider_id, provider in context.provider_manager.inst_map.items():
                    if hasattr(provider, "get_embedding"):
                        embedding_providers.append(provider)
                        logger.debug(f"Found embedding provider: {provider_id}")

            if not embedding_providers:
                logger.debug("No embedding providers available")
                return None

            # 使用第一个可用的 embedding provider
            provider = embedding_providers[0]
            logger.info("Using first available embedding provider")
            return AstrBotEmbeddingAdapter(provider)

        except Exception as e:
            logger.debug(f"Failed to create native embedding adapter: {e}")
            return None

    @staticmethod
    def _try_legacy_provider(config: dict, logger) -> Optional[LegacyEmbeddingAdapter]:
        """尝试使用传统嵌入服务实现"""
        try:
            # 检查必要的配置
            required_keys = ["embedding_model", "embedding_key"]
            missing_keys = [key for key in required_keys if not config.get(key)]

            if missing_keys:
                logger.debug(f"Missing legacy embedding config: {missing_keys}")
                return None

            embedding_service = config.get("embedding_service", "openai").lower()

            if embedding_service == "gemini":
                from .embedding import GeminiEmbeddingAPI

                service = GeminiEmbeddingAPI(
                    model=config.get("embedding_model"),
                    api_key=config.get("embedding_key"),
                )
                logger.info("Created legacy Gemini embedding adapter")
                return LegacyEmbeddingAdapter(service, "Gemini")

            elif embedding_service == "openai":
                from .embedding import OpenAIEmbeddingAPI

                service = OpenAIEmbeddingAPI(
                    model=config.get("embedding_model"),
                    api_key=config.get("embedding_key"),
                    base_url=config.get("embedding_url"),
                )
                logger.info("Created legacy OpenAI embedding adapter")
                return LegacyEmbeddingAdapter(service, "OpenAI")

            else:
                logger.error(
                    f"Unsupported legacy embedding service: {embedding_service}"
                )
                return None

        except Exception as e:
            logger.debug(f"Failed to create legacy embedding adapter: {e}")
            return None

    @staticmethod
    def get_supported_services() -> List[str]:
        """获取支持的嵌入服务列表"""
        return ["astrbot_native", "openai", "gemini"]

    @staticmethod
    def validate_config(config: dict) -> tuple[bool, str]:
        """
        验证嵌入服务配置

        Args:
            config: 配置字典

        Returns:
            (is_valid, error_message) 元组
        """
        try:
            # 检查是否配置了原生 provider ID
            if config.get("embedding_provider_id"):
                return True, ""

            # 检查传统配置
            embedding_service = config.get("embedding_service", "").lower()
            if embedding_service in ["openai", "gemini"]:
                required_keys = ["embedding_model", "embedding_key"]
                missing_keys = [key for key in required_keys if not config.get(key)]

                if missing_keys:
                    return False, f"Missing required embedding config: {missing_keys}"

                return True, ""

            return False, "No valid embedding service configuration found"

        except Exception as e:
            return False, f"Config validation error: {e}"
