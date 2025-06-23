# -*- coding: utf-8 -*-
"""
向量数据库工厂类
支持创建和管理不同类型的向量数据库实例
"""

from typing import Dict, Any, Optional
from astrbot.core.log import LogManager

from ..vector_db_base import VectorDatabase
from .milvus_manager import MilvusManager
from .faiss_manager import FaissManager


class VectorDatabaseFactory:
    """
    向量数据库工厂类
    负责根据配置创建合适的向量数据库实例
    """

    @staticmethod
    def create_database(
        db_type: str, config: Dict[str, Any], logger: Optional[LogManager] = None
    ) -> Optional[VectorDatabase]:
        """
        创建向量数据库实例

        Args:
            db_type: 数据库类型 ("milvus" 或 "faiss")
            config: 数据库配置
            logger: 日志记录器

        Returns:
            VectorDatabase 实例或 None（如果创建失败）
        """
        if logger is None:
            logger = LogManager.GetLogger(log_name="VectorDatabaseFactory")

        try:
            db_type_lower = db_type.lower()

            if db_type_lower == "milvus":
                return VectorDatabaseFactory._create_milvus_database(config, logger)
            elif db_type_lower == "faiss":
                return VectorDatabaseFactory._create_faiss_database(config, logger)
            else:
                logger.error(f"Unsupported database type: {db_type}")
                return None

        except Exception as e:
            logger.error(f"Failed to create {db_type} database: {e}", exc_info=True)
            return None

    @staticmethod
    def _create_milvus_database(
        config: Dict[str, Any], logger
    ) -> Optional[MilvusManager]:
        """创建 Milvus 数据库实例"""
        try:
            # 提取 Milvus 配置参数
            connect_args = {}

            # Milvus Lite 路径
            lite_path = config.get("milvus_lite_path", "")
            if lite_path:
                connect_args["lite_path"] = lite_path
                logger.info(f"Using Milvus Lite with path: {lite_path}")
            else:
                # 标准 Milvus 配置
                address = config.get("address", "")
                if address:
                    if address.startswith(("http://", "https://", "unix:")):
                        connect_args["uri"] = address
                    else:
                        # 解析 host:port
                        if ":" in address:
                            host, port = address.rsplit(":", 1)
                            connect_args["host"] = host
                            connect_args["port"] = port
                        else:
                            connect_args["host"] = address
                            connect_args["port"] = "19530"

                # 认证配置
                auth_config = config.get("authentication", {})
                if auth_config:
                    for key in ["user", "password", "token", "secure"]:
                        if key in auth_config and auth_config[key] is not None:
                            if key == "secure":
                                connect_args[key] = bool(auth_config[key])
                            else:
                                connect_args[key] = auth_config[key]

            # 数据库名称
            db_name = config.get("db_name", "default")
            if db_name != "default":
                connect_args["db_name"] = db_name

            # 连接别名
            collection_name = config.get("collection_name", "default")
            connect_args["alias"] = config.get(
                "connection_alias", f"mnemosyne_{collection_name}"
            )

            # 创建 MilvusManager 实例
            milvus_manager = MilvusManager(**connect_args)

            logger.info("Successfully created Milvus database instance")
            return milvus_manager

        except Exception as e:
            logger.error(f"Failed to create Milvus database: {e}", exc_info=True)
            return None

    @staticmethod
    def _create_faiss_database(
        config: Dict[str, Any], logger
    ) -> Optional[FaissManager]:
        """创建 FAISS 数据库实例"""
        try:
            # 提取 FAISS 配置参数
            faiss_config = config.get("faiss_config", {})
            data_path = faiss_config.get("faiss_data_path", "faiss_data")
            index_type = faiss_config.get("faiss_index_type", "IndexFlatL2")
            nlist = faiss_config.get("faiss_nlist", 100)

            # 创建 FaissManager 实例
            faiss_manager = FaissManager(
                data_path=data_path, index_type=index_type, nlist=nlist
            )

            logger.info(
                f"Successfully created FAISS database instance with path: {data_path}"
            )
            return faiss_manager

        except Exception as e:
            logger.error(f"Failed to create FAISS database: {e}", exc_info=True)
            return None

    @staticmethod
    def get_supported_databases() -> list[str]:
        """获取支持的数据库类型列表"""
        return ["milvus", "faiss"]

    @staticmethod
    def validate_config(db_type: str, config: Dict[str, Any]) -> tuple[bool, str]:
        """
        验证数据库配置

        Args:
            db_type: 数据库类型
            config: 配置字典

        Returns:
            (is_valid, error_message) 元组
        """
        try:
            db_type_lower = db_type.lower()

            if db_type_lower == "milvus":
                return VectorDatabaseFactory._validate_milvus_config(config)
            elif db_type_lower == "faiss":
                return VectorDatabaseFactory._validate_faiss_config(config)
            else:
                return False, f"Unsupported database type: {db_type}"

        except Exception as e:
            return False, f"Config validation error: {e}"

    @staticmethod
    def _validate_milvus_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """验证 Milvus 配置"""
        # 检查是否配置了 Lite 路径或标准地址
        lite_path = config.get("milvus_lite_path", "")
        address = config.get("address", "")

        if not lite_path and not address:
            return (
                False,
                "Either 'milvus_lite_path' or 'address' must be configured for Milvus",
            )

        # 如果配置了认证，检查必要字段
        auth_config = config.get("authentication", {})
        if auth_config:
            if auth_config.get("user") and not auth_config.get("password"):
                return False, "Password is required when user is specified"

        return True, ""

    @staticmethod
    def _validate_faiss_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """验证 FAISS 配置"""
        faiss_config = config.get("faiss_config", {})

        # 检查数据路径
        data_path = faiss_config.get("faiss_data_path", "faiss_data")
        if not isinstance(data_path, str) or not data_path.strip():
            return False, "Invalid 'faiss_data_path' configuration"

        # 检查索引类型
        index_type = faiss_config.get("faiss_index_type", "IndexFlatL2")
        supported_types = [
            "IndexFlatL2",
            "IndexFlatIP",
            "IndexIVFFlat",
            "IndexHNSWFlat",
        ]
        if index_type not in supported_types:
            return (
                False,
                f"Unsupported FAISS index type: {index_type}. Supported types: {supported_types}",
            )

        # 检查 nlist 参数（仅对 IVF 索引有效）
        if index_type == "IndexIVFFlat":
            nlist = faiss_config.get("faiss_nlist", 100)
            if not isinstance(nlist, int) or nlist <= 0:
                return False, "Invalid 'faiss_nlist' configuration for IndexIVFFlat"

        return True, ""

    @staticmethod
    def get_default_config(db_type: str) -> Dict[str, Any]:
        """
        获取指定数据库类型的默认配置

        Args:
            db_type: 数据库类型

        Returns:
            默认配置字典
        """
        db_type_lower = db_type.lower()

        if db_type_lower == "milvus":
            return {
                "milvus_lite_path": "",
                "address": "",
                "authentication": {
                    "user": "",
                    "password": "",
                    "token": "",
                    "secure": False,
                },
                "db_name": "default",
                "connection_alias": "",
                "collection_name": "mnemosyne_default",
            }
        elif db_type_lower == "faiss":
            return {
                "faiss_config": {
                    "faiss_data_path": "faiss_data",
                    "faiss_index_type": "IndexFlatL2",
                    "faiss_nlist": 100,
                }
            }
        else:
            return {}

    @staticmethod
    def migrate_data(
        source_db: VectorDatabase,
        target_db: VectorDatabase,
        collection_name: str,
        batch_size: int = 1000,
    ) -> bool:
        """
        在不同数据库之间迁移数据

        Args:
            source_db: 源数据库
            target_db: 目标数据库
            collection_name: 集合名称
            batch_size: 批处理大小

        Returns:
            迁移是否成功
        """
        logger = LogManager.GetLogger(log_name="DatabaseMigration")

        try:
            # 检查源集合是否存在
            if not source_db.has_collection(collection_name):
                logger.error(f"Source collection '{collection_name}' does not exist")
                return False

            # 获取源集合的所有数据
            all_data = source_db.query(
                collection_name=collection_name,
                filters="memory_id >= 0",  # 获取所有记录
                output_fields=["*"],  # 获取所有字段
                limit=None,
            )

            if not all_data:
                logger.info(f"No data found in source collection '{collection_name}'")
                return True

            # 获取源集合的 schema
            source_stats = source_db.get_collection_stats(collection_name)
            schema = {
                "vector_dim": source_stats.get("vector_dim", 1024),
                "fields": [],  # 简化的 schema
            }

            # 在目标数据库中创建集合
            if not target_db.create_collection(collection_name, schema):
                logger.error(f"Failed to create target collection '{collection_name}'")
                return False

            # 分批迁移数据
            total_records = len(all_data)
            migrated_count = 0

            for i in range(0, total_records, batch_size):
                batch_data = all_data[i : i + batch_size]

                if target_db.insert(collection_name, batch_data):
                    migrated_count += len(batch_data)
                    logger.info(f"Migrated {migrated_count}/{total_records} records")
                else:
                    logger.error(f"Failed to migrate batch {i // batch_size + 1}")
                    return False

            logger.info(
                f"Successfully migrated {migrated_count} records from {source_db.get_database_type().value} to {target_db.get_database_type().value}"
            )
            return True

        except Exception as e:
            logger.error(f"Data migration failed: {e}", exc_info=True)
            return False
