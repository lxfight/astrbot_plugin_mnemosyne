"""
Milvus 适配器实现
使用适配器模式将 MilvusManager 适配到 VectorDatabase 接口
"""

from __future__ import annotations

from typing import Any

from pymilvus import Collection

from astrbot.core.log import LogManager

from ..vector_db_base import VectorDatabase, VectorDeleteResult, VectorInsertResult
from .milvus_manager import MilvusManager
from .schema_utils import collection_schema_to_dict, dict_to_collection_schema

logger = LogManager.GetLogger(log_name="Mnemosyne MilvusAdapter")


class MilvusVectorDB(VectorDatabase):
    """
    Milvus 向量数据库适配器

    使用适配器模式将 MilvusManager 适配到 VectorDatabase 接口，
    提供统一的向量数据库操作接口。

    该类使用组合模式，内部持有 MilvusManager 实例，
    并实现所有 VectorDatabase 抽象方法。
    """

    def __init__(
        self,
        alias: str = "default",
        lite_path: str | None = None,
        uri: str | None = None,
        host: str | None = None,
        port: str | int | None = None,
        user: str | None = None,
        password: str | None = None,
        secure: bool | None = None,
        token: str | None = None,
        db_name: str = "default",
        **kwargs,
    ):
        """
        初始化 MilvusVectorDB 适配器

        Args:
            alias (str): 此连接的别名
            lite_path (Optional[str]): Milvus Lite 数据文件的本地路径
            uri (Optional[str]): 标准 Milvus 连接 URI
            host (Optional[str]): Milvus 服务器主机名/IP
            port (Optional[Union[str, int]]): Milvus 服务器端口
            user (Optional[str]): 标准 Milvus 认证用户名
            password (Optional[str]): 标准 Milvus 认证密码
            secure (Optional[bool]): 是否对标准 Milvus 连接使用 TLS/SSL
            token (Optional[str]): 标准 Milvus 认证 Token/API Key
            db_name (str): 要连接的数据库名称
            **kwargs: 传递给 MilvusManager 的其他参数
        """
        # 创建 MilvusManager 实例
        self._manager = MilvusManager(
            alias=alias,
            lite_path=lite_path,
            uri=uri,
            host=host,
            port=port,
            user=user,
            password=password,
            secure=secure,
            token=token,
            db_name=db_name,
            **kwargs,
        )

        # 集合缓存，用于提高性能
        self._collection_cache: dict[str, Collection] = {}
        self._is_connected = False

        logger.info(f"MilvusVectorDB 适配器已初始化 (别名: {alias})")

    # --- VectorDatabase 抽象方法实现 ---

    def connect(self, **kwargs):
        """
        连接到数据库

        Args:
            **kwargs: 额外的连接参数（当前未使用，保留用于扩展）
        """
        try:
            self._manager.connect()
            self._is_connected = self._manager.is_connected()
            logger.info("MilvusVectorDB 已成功连接")
        except Exception as e:
            self._is_connected = False
            logger.error(f"MilvusVectorDB 连接失败: {e}")
            raise

    def is_connected(self) -> bool:
        """返回当前连接状态。"""
        self._is_connected = self._manager.is_connected()
        return self._is_connected

    def create_collection(self, collection_name: str, schema: dict[str, Any]):
        """
        创建集合（表）

        Args:
            collection_name (str): 集合名称
            schema (Dict[str, Any]): 集合的字段定义
        """
        try:
            # 将字典格式转换为 CollectionSchema 对象
            collection_schema = dict_to_collection_schema(schema)

            # 使用 MilvusManager 创建集合
            collection = self._manager.create_collection(
                collection_name=collection_name, schema=collection_schema
            )

            if collection:
                # 缓存新创建的集合
                self._collection_cache[collection_name] = collection
                logger.info(f"集合 '{collection_name}' 创建成功")
            else:
                logger.error(f"集合 '{collection_name}' 创建失败")

        except Exception as e:
            logger.error(f"创建集合 '{collection_name}' 失败: {e}")
            raise

    def insert(
        self, collection_name: str, data: list[dict[str, Any]]
    ) -> VectorInsertResult:
        """
        插入数据

        Args:
            collection_name (str): 集合名称
            data (List[Dict[str, Any]]): 数据列表，每个元素是一个字典
        """
        try:
            # 使用 MilvusManager 插入数据
            # M24 修复: 添加类型忽略注释，Milvus SDK 的类型定义较宽松
            result = self._manager.insert(collection_name=collection_name, data=data)  # type: ignore

            if result:
                logger.info(f"成功向集合 '{collection_name}' 插入 {len(data)} 条数据")
                insert_count = getattr(result, "insert_count", len(data))
                primary_keys = list(getattr(result, "primary_keys", []) or [])
                return VectorInsertResult(
                    insert_count=insert_count,
                    primary_keys=primary_keys,
                )
            else:
                logger.error(f"向集合 '{collection_name}' 插入数据失败")
                return VectorInsertResult()

        except Exception as e:
            logger.error(f"插入数据到集合 '{collection_name}' 失败: {e}")
            raise

    def query(
        self,
        collection_name: str,
        filters: str | None,
        output_fields: list[str] | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        根据条件查询数据

        Args:
            collection_name (str): 集合名称
            filters (str): 查询条件表达式
            output_fields (List[str]): 返回的字段列表

        Returns:
            List[Dict[str, Any]]: 查询结果
        """
        try:
            # 使用 MilvusManager 查询数据
            results = self._manager.query(
                collection_name=collection_name,
                expression=filters or "memory_id >= 0",
                output_fields=output_fields,
                limit=limit,
                offset=offset,
            )

            if results is not None:
                logger.info(f"从集合 '{collection_name}' 查询到 {len(results)} 条结果")
                return results
            else:
                logger.warning(f"从集合 '{collection_name}' 查询结果为空")
                return []

        except Exception as e:
            logger.error(f"查询集合 '{collection_name}' 失败: {e}")
            raise

    def get_by_id(
        self,
        collection_name: str,
        record_id: str,
        output_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """通过 Milvus 主键直接读取记录。"""
        try:
            normalized_id = int(record_id)
            filters = f"memory_id == {normalized_id}"
        except ValueError:
            filters = f'memory_id == "{record_id}"'
        records = self.query(
            collection_name=collection_name,
            filters=filters,
            output_fields=output_fields,
            limit=1,
        )
        return records[0] if records else None

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: str | None = None,
        search_params: dict[str, Any] | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        执行相似性搜索

        Args:
            collection_name (str): 集合名称
            query_vector (List[float]): 查询向量
            top_k (int): 返回的最相似结果数量
            filters (str, optional): 可选的过滤条件

        Returns:
            List[Dict[str, Any]]: 搜索结果
        """
        try:
            # 获取集合信息以确定向量字段名
            collection = self._get_collection(collection_name)
            if not collection:
                raise ValueError(f"集合 '{collection_name}' 不存在")

            # 查找向量字段
            vector_field = None
            for field in collection.schema.fields:
                if field.dtype.name in ["FLOAT_VECTOR", "BINARY_VECTOR"]:
                    vector_field = field.name
                    break

            if not vector_field:
                raise ValueError(f"集合 '{collection_name}' 中未找到向量字段")

            # 使用 MilvusManager 执行搜索
            raw_results = self._manager.search(
                collection_name=collection_name,
                query_vectors=[query_vector],
                vector_field=vector_field,
                search_params=search_params
                or {"metric_type": "L2", "params": {"nprobe": 10}},
                limit=top_k,
                expression=filters,
                output_fields=output_fields or ["*"],
            )

            # 格式化搜索结果并转为业务层直接使用的扁平记录
            formatted_results = [
                self._flatten_search_result(item)
                for item in self._manager.format_search_results(raw_results)
            ]

            logger.info(
                f"从集合 '{collection_name}' 搜索到 {len(formatted_results)} 条结果"
            )
            return formatted_results

        except Exception as e:
            logger.error(f"搜索集合 '{collection_name}' 失败: {e}")
            raise

    def close(self):
        """
        关闭数据库连接
        """
        try:
            self._manager.disconnect()
            self._is_connected = False
            # 清空集合缓存
            self._collection_cache.clear()
            logger.info("MilvusVectorDB 连接已关闭")
        except Exception as e:
            logger.error(f"关闭 MilvusVectorDB 连接失败: {e}")
            raise

    def list_collections(self) -> list[str]:
        """
        获取所有集合名称

        Returns:
            List[str]: 集合名称列表
        """
        try:
            collections = self._manager.list_collections()
            logger.info(f"获取到 {len(collections)} 个集合")
            return collections
        except Exception as e:
            logger.error(f"获取集合列表失败: {e}")
            raise

    def has_collection(self, collection_name: str) -> bool:
        """判断集合是否存在。"""
        return self._manager.has_collection(collection_name)

    def get_loaded_collections(self) -> list[str]:
        """
        获取已加载到内存的集合

        Returns:
            List[str]: 已加载集合名称列表
        """
        try:
            loaded_collections = []
            for collection_name in self.list_collections():
                collection = self._get_collection(collection_name)
                if collection:
                    # 检查集合加载状态
                    try:
                        # 使用 Milvus 的 utility 函数检查加载状态
                        from pymilvus import utility

                        progress = utility.loading_progress(
                            collection_name, using=self._manager.alias
                        )
                        if progress and progress.get("loading_progress") == 100:
                            loaded_collections.append(collection_name)
                    except Exception as e:
                        logger.warning(
                            f"检查集合 '{collection_name}' 加载状态失败: {e}"
                        )

            logger.info(f"获取到 {len(loaded_collections)} 个已加载集合")
            return loaded_collections
        except Exception as e:
            logger.error(f"获取已加载集合列表失败: {e}")
            raise

    def get_latest_memory(
        self, collection_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        获取最新插入的记忆

        Args:
            collection_name (str): 集合名称
            limit (int): 返回的最大记录数

        Returns:
            List[Dict[str, Any]]: 最新的记忆记录
        """
        try:
            # 使用 MilvusManager 查询最新记录
            results = self._manager.query(
                collection_name=collection_name,
                expression="",  # 空表达式表示所有记录
                output_fields=["*"],
                limit=limit,
            )

            if results:
                # 按时间戳降序排序（如果结果不为空）
                results.sort(key=lambda x: x.get("create_time", 0), reverse=True)
                logger.info(
                    f"从集合 '{collection_name}' 获取到 {len(results)} 条最新记忆"
                )
            else:
                logger.warning(f"集合 '{collection_name}' 中没有数据")

            return results if results else []

        except Exception as e:
            logger.error(f"获取集合 '{collection_name}' 的最新记忆失败: {e}")
            raise

    def delete(self, collection_name: str, expr: str) -> VectorDeleteResult:
        """
        根据条件删除记忆

        Args:
            collection_name (str): 集合名称
            expr (str): 删除条件表达式
        """
        try:
            # 使用 MilvusManager 删除数据
            result = self._manager.delete(
                collection_name=collection_name, expression=expr
            )

            if result:
                logger.info(
                    f"成功从集合 '{collection_name}' 删除匹配条件 '{expr}' 的记录"
                )
                delete_count = getattr(result, "delete_count", None)
                return VectorDeleteResult(delete_count=delete_count)
            else:
                logger.error(f"从集合 '{collection_name}' 删除记录失败")
                return VectorDeleteResult(delete_count=0)

        except Exception as e:
            logger.error(f"从集合 '{collection_name}' 删除记录失败: {e}")
            raise

    def flush(self, collection_names: list[str] | None = None) -> bool:
        """刷新集合，确保写入/删除尽快可见。"""
        return self._manager.flush(collection_names)

    def drop_collection(self, collection_name: str) -> bool:
        """
        删除指定的集合（包括其下的所有数据）

        Args:
            collection_name (str): 要删除的集合名称
        """
        try:
            # 从缓存中移除集合
            if collection_name in self._collection_cache:
                del self._collection_cache[collection_name]

            # 使用 MilvusManager 删除集合
            success = self._manager.drop_collection(collection_name)

            if success:
                logger.info(f"成功删除集合 '{collection_name}'")
            else:
                logger.error(f"删除集合 '{collection_name}' 失败")
            return bool(success)

        except Exception as e:
            logger.error(f"删除集合 '{collection_name}' 失败: {e}")
            raise

    # --- 业务特定方法 ---

    def check_collection_schema_consistency(
        self, collection_name: str, expected_schema: dict[str, Any]
    ) -> bool:
        """
        检查集合的 Schema 是否与预期一致

        Args:
            collection_name (str): 集合名称
            expected_schema (Dict[str, Any]): 预期的 Schema 定义

        Returns:
            bool: True 如果一致，False 如果不一致
        """
        try:
            # 获取集合
            collection = self._get_collection(collection_name)
            if not collection:
                logger.warning(f"集合 '{collection_name}' 不存在，无法检查一致性")
                return False

            # 将集合的 Schema 转换为字典格式
            actual_schema_dict = collection_schema_to_dict(collection.schema)

            # 比较字段定义
            expected_fields = {
                field["name"]: field for field in expected_schema.get("fields", [])
            }
            actual_fields = {
                field["name"]: field for field in actual_schema_dict.get("fields", [])
            }

            # 检查所有预期字段是否存在且类型匹配
            for field_name, expected_field in expected_fields.items():
                if field_name not in actual_fields:
                    logger.warning(f"集合 '{collection_name}' 缺少字段 '{field_name}'")
                    return False

                actual_field = actual_fields[field_name]
                if actual_field["dtype"] != expected_field["dtype"]:
                    logger.warning(
                        f"集合 '{collection_name}' 字段 '{field_name}' 类型不匹配: "
                        f"期望 {expected_field['dtype']}, 实际 {actual_field['dtype']}"
                    )
                    return False

                # 检查特定类型的参数
                if expected_field["dtype"] in [
                    "VARCHAR",
                    "FLOAT_VECTOR",
                    "BINARY_VECTOR",
                ]:
                    if expected_field["dtype"] == "VARCHAR":
                        if expected_field.get("max_length") != actual_field.get(
                            "max_length"
                        ):
                            logger.warning(
                                f"集合 '{collection_name}' 字段 '{field_name}' 的 max_length 不匹配"
                            )
                            return False
                    else:  # FLOAT_VECTOR or BINARY_VECTOR
                        if expected_field.get("dim") != actual_field.get("dim"):
                            logger.warning(
                                f"集合 '{collection_name}' 字段 '{field_name}' 的维度不匹配"
                            )
                            return False

            # 检查是否有额外字段
            extra_fields = set(actual_fields.keys()) - set(expected_fields.keys())
            if extra_fields:
                logger.warning(f"集合 '{collection_name}' 包含额外字段: {extra_fields}")
                # 根据策略决定是否视为不一致

            logger.info(f"集合 '{collection_name}' 的 Schema 与预期一致")
            return True

        except Exception as e:
            logger.error(f"检查集合 '{collection_name}' Schema 一致性失败: {e}")
            return False

    # --- 上下文管理器支持 ---

    def __enter__(self):
        """
        支持with语句，进入时确保连接
        """
        try:
            self.connect()
            return self
        except Exception as e:
            logger.error(f"进入 MilvusVectorDB 上下文管理器时连接失败: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        支持with语句，退出时断开连接
        """
        try:
            self.close()
        except Exception as e:
            logger.error(f"退出 MilvusVectorDB 上下文管理器时断开连接失败: {e}")

        # 如果有异常，记录但不抑制
        if exc_type:
            logger.error(
                f"MilvusVectorDB 上下文管理器退出时捕获到异常: {exc_type.__name__}: {exc_val}"
            )

    # --- 私有辅助方法 ---

    def _get_collection(self, collection_name: str) -> Collection | None:
        """
        获取集合对象，使用缓存提高性能

        Args:
            collection_name (str): 集合名称

        Returns:
            Optional[Collection]: 集合对象，如果不存在则返回 None
        """
        # 检查缓存
        if collection_name in self._collection_cache:
            return self._collection_cache[collection_name]

        # 从 MilvusManager 获取集合
        collection = self._manager.get_collection(collection_name)
        if collection:
            # 缓存集合对象
            self._collection_cache[collection_name] = collection

            return collection

    @staticmethod
    def _flatten_search_result(result: dict[str, Any]) -> dict[str, Any]:
        """将 MilvusManager 的统一搜索包装转成记忆记录。"""
        entity = result.get("entity", {})
        if (
            isinstance(entity, dict)
            and "entity" in entity
            and isinstance(entity.get("entity"), dict)
        ):
            entity = entity["entity"]
        record = dict(entity) if isinstance(entity, dict) else {}
        if "id" not in record and "memory_id" not in record:
            record["id"] = result.get("id")
        distance = result.get("distance")
        if isinstance(distance, (int, float)):
            record["_distance"] = float(distance)
        score = result.get("score")
        if isinstance(score, (int, float)):
            record["_score"] = float(score)
        return record

    def get_connection_info(self) -> dict[str, Any]:
        """
        获取连接信息，用于调试

        Returns:
            Dict[str, Any]: 连接信息字典
        """
        return self._manager.get_connection_info()
