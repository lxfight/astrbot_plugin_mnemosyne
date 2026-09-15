"""
向量数据库工厂模块
根据配置动态创建不同类型的向量数据库实例
"""

from typing import Any

from astrbot.core.log import LogManager

from ..vector_db_base import VectorDatabase

logger = LogManager.GetLogger(log_name="Mnemosyne VectorDBFactory")

MilvusVectorDB = None
ChromaVectorDB = None
QdrantVectorDB = None
WeaviateVectorDB = None


def _load_vector_db_class(db_type: str):
    """Lazy-load adapters so optional database dependencies stay optional."""
    global MilvusVectorDB, ChromaVectorDB, QdrantVectorDB, WeaviateVectorDB

    if db_type == "milvus":
        if MilvusVectorDB is None:
            from .milvus_adapter import MilvusVectorDB as _MilvusVectorDB

            MilvusVectorDB = _MilvusVectorDB
        return MilvusVectorDB
    if db_type == "chroma":
        if ChromaVectorDB is None:
            from .chroma_adapter import ChromaVectorDB as _ChromaVectorDB

            ChromaVectorDB = _ChromaVectorDB
        return ChromaVectorDB
    if db_type == "qdrant":
        if QdrantVectorDB is None:
            from .qdrant_adapter import QdrantVectorDB as _QdrantVectorDB

            QdrantVectorDB = _QdrantVectorDB
        return QdrantVectorDB
    if db_type == "weaviate":
        if WeaviateVectorDB is None:
            from .weaviate_adapter import WeaviateVectorDB as _WeaviateVectorDB

            WeaviateVectorDB = _WeaviateVectorDB
        return WeaviateVectorDB

    raise ValueError(f"不支持的向量数据库类型: {db_type}")


class VectorDatabaseFactory:
    """
    向量数据库工厂类
    负责根据配置创建不同类型的向量数据库实例
    """

    @staticmethod
    def create_vector_db(
        db_type: str, config: dict[str, Any], plugin_data_dir: str | None = None
    ) -> VectorDatabase:
        """
        根据数据库类型创建相应的向量数据库实例

        Args:
            db_type: 数据库类型 ('milvus', 'chroma', 'qdrant', 'weaviate')
            config: 数据库配置字典
            plugin_data_dir: 插件数据目录路径

        Returns:
            VectorDatabase: 向量数据库实例

        Raises:
            ValueError: 如果数据库类型不支持
            RuntimeError: 如果创建数据库实例失败
        """
        db_type = db_type.lower().strip()

        logger.info(f"正在创建 {db_type} 类型的向量数据库实例...")

        if db_type == "milvus":
            return VectorDatabaseFactory._create_milvus(config, plugin_data_dir)
        elif db_type == "chroma":
            return VectorDatabaseFactory._create_chroma(config, plugin_data_dir)
        elif db_type == "qdrant":
            return VectorDatabaseFactory._create_qdrant(config, plugin_data_dir)
        elif db_type == "weaviate":
            return VectorDatabaseFactory._create_weaviate(config, plugin_data_dir)
        else:
            raise ValueError(
                f"不支持的向量数据库类型: {db_type}。"
                f"支持的类型: milvus, chroma, qdrant, weaviate"
            )

    @staticmethod
    def _create_milvus(
        config: dict[str, Any], plugin_data_dir: str | None = None
    ) -> VectorDatabase:
        """
        创建 Milvus 向量数据库实例

        Args:
            config: Milvus 配置
            plugin_data_dir: 插件数据目录

        Returns:
            VectorDatabase: Milvus 数据库实例
        """
        # 构建 Milvus 连接参数
        connect_args = {}

        # Milvus Lite 路径配置
        lite_path = config.get("milvus_lite_path", "")
        if lite_path:
            connect_args["lite_path"] = lite_path

        # 标准 Milvus 地址配置
        address = config.get("address", "")
        if address:
            # 判断是 URI 还是 host:port
            if address.startswith(("http://", "https://", "unix:")):
                connect_args["uri"] = address
            else:
                # 解析 host:port
                try:
                    from ...core.tools import parse_address
                except ImportError:
                    from core.tools import parse_address
                try:
                    host, port = parse_address(address)
                    connect_args["host"] = host
                    connect_args["port"] = port
                except ValueError as e:
                    raise ValueError(f"解析 Milvus 地址失败: {e}") from e

        # 数据库名称
        db_name = config.get("db_name", "default")
        if db_name != "default":
            connect_args["db_name"] = db_name

        # 认证信息
        auth_config = config.get("authentication", {})
        if auth_config:
            for key in ["user", "password", "token", "secure"]:
                if key in auth_config and auth_config[key] is not None:
                    if key == "secure" and isinstance(auth_config[key], str):
                        connect_args[key] = auth_config[key].lower() == "true"
                    else:
                        connect_args[key] = auth_config[key]

        # 连接别名
        alias = config.get("connection_alias", "mnemosyne_default")
        connect_args["alias"] = alias

        # 插件数据目录
        if plugin_data_dir:
            connect_args["plugin_data_dir"] = plugin_data_dir

        logger.info(f"使用以下参数创建 Milvus 数据库 (别名: {alias})")
        logger.debug(f"Milvus 连接参数: {connect_args}")

        try:
            vector_db_class = _load_vector_db_class("milvus")
            return vector_db_class(**connect_args)
        except Exception as e:
            logger.error(f"创建 Milvus 数据库实例失败: {e}", exc_info=True)
            raise RuntimeError(f"无法创建 Milvus 数据库实例: {e}") from e

    @staticmethod
    def _create_chroma(
        config: dict[str, Any], plugin_data_dir: str | None = None
    ) -> VectorDatabase:
        """
        创建 Chroma 向量数据库实例

        Args:
            config: Chroma 配置
            plugin_data_dir: 插件数据目录

        Returns:
            VectorDatabase: Chroma 数据库实例
        """
        # 获取 Chroma 配置
        chroma_config = config.get("chroma_config", {})

        # 持久化目录
        persist_directory = chroma_config.get("persist_directory", "")
        if not persist_directory and plugin_data_dir:
            # 使用默认目录
            from pathlib import Path

            persist_directory = str(Path(plugin_data_dir) / "chroma_data")

        # 客户端模式配置
        host = chroma_config.get("host", "")
        port = chroma_config.get("port", 8000)

        logger.info("创建 Chroma 向量数据库实例")

        try:
            vector_db_class = _load_vector_db_class("chroma")
            if host:
                # 使用客户端模式
                logger.info(f"使用 Chroma 客户端模式: {host}:{port}")
                return vector_db_class(host=host, port=port, persist_directory=None)
            else:
                # 使用本地持久化模式
                logger.info(f"使用 Chroma 本地持久化模式: {persist_directory}")
                return vector_db_class(
                    persist_directory=persist_directory, host=None, port=None
                )
        except Exception as e:
            logger.error(f"创建 Chroma 数据库实例失败: {e}", exc_info=True)
            raise RuntimeError(f"无法创建 Chroma 数据库实例: {e}") from e

    @staticmethod
    def _create_qdrant(
        config: dict[str, Any], plugin_data_dir: str | None = None
    ) -> VectorDatabase:
        """
        创建 Qdrant 向量数据库实例

        Args:
            config: Qdrant 配置
            plugin_data_dir: 插件数据目录

        Returns:
            VectorDatabase: Qdrant 数据库实例
        """
        # 获取 Qdrant 配置
        qdrant_config = config.get("qdrant_config", {})

        # 持久化路径
        path = qdrant_config.get("path", "")
        if not path and plugin_data_dir:
            # 使用默认目录
            from pathlib import Path

            path = str(Path(plugin_data_dir) / "qdrant_data")

        # 客户端模式配置
        url = qdrant_config.get("url", "")
        api_key = qdrant_config.get("api_key", "")

        # 集合配置
        collection_config = {
            "vector_size": config.get("embedding_dim", 768),
            "distance": qdrant_config.get("distance", "Cosine"),
        }

        logger.info("创建 Qdrant 向量数据库实例")

        try:
            vector_db_class = _load_vector_db_class("qdrant")
            if url:
                # 使用客户端模式
                logger.info(f"使用 Qdrant 客户端模式: {url}")
                return vector_db_class(
                    url=url,
                    api_key=api_key if api_key else None,
                    collection_config=collection_config,
                )
            else:
                # 使用本地持久化模式
                logger.info(f"使用 Qdrant 本地持久化模式: {path}")
                return vector_db_class(
                    path=path,
                    collection_config=collection_config,
                )
        except Exception as e:
            logger.error(f"创建 Qdrant 数据库实例失败: {e}", exc_info=True)
            raise RuntimeError(f"无法创建 Qdrant 数据库实例: {e}") from e

    @staticmethod
    def _create_weaviate(
        config: dict[str, Any], plugin_data_dir: str | None = None
    ) -> VectorDatabase:
        """
        创建 Weaviate 向量数据库实例

        Args:
            config: Weaviate 配置
            plugin_data_dir: 插件数据目录

        Returns:
            VectorDatabase: Weaviate 数据库实例
        """
        # 获取 Weaviate 配置
        weaviate_config = config.get("weaviate_config", {})

        # 嵌入式模式
        embedded = weaviate_config.get("embedded", False)
        persistence_data_path = weaviate_config.get("persistence_data_path", "")

        if embedded and not persistence_data_path and plugin_data_dir:
            from pathlib import Path

            persistence_data_path = str(Path(plugin_data_dir) / "weaviate_data")

        # 客户端模式
        url = weaviate_config.get("url", "")
        api_key = weaviate_config.get("api_key", "")

        # 额外的 HTTP 头（如 OpenAI API key）
        additional_headers = weaviate_config.get("additional_headers", {})

        logger.info("创建 Weaviate 向量数据库实例")

        try:
            vector_db_class = _load_vector_db_class("weaviate")
            if embedded:
                # 使用嵌入式模式
                logger.info(f"使用 Weaviate 嵌入式模式: {persistence_data_path}")
                return vector_db_class(
                    embedded=True,
                    persistence_data_path=persistence_data_path,
                )
            else:
                # 使用客户端模式
                logger.info(f"使用 Weaviate 客户端模式: {url}")
                return vector_db_class(
                    url=url,
                    api_key=api_key if api_key else None,
                    additional_headers=additional_headers,
                )
        except Exception as e:
            logger.error(f"创建 Weaviate 数据库实例失败: {e}", exc_info=True)
            raise RuntimeError(f"无法创建 Weaviate 数据库实例: {e}") from e
