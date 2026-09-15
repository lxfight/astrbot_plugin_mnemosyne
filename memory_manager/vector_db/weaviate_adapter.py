"""
Weaviate 向量数据库适配器
实现 VectorDatabase 接口，提供统一的 Weaviate 数据库操作
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from astrbot.core.log import LogManager

from ..vector_db_base import VectorDatabase, VectorDeleteResult, VectorInsertResult

logger = LogManager.GetLogger(log_name="Mnemosyne WeaviateAdapter")


class WeaviateVectorDB(VectorDatabase):
    """
    Weaviate 向量数据库适配器

    支持两种模式：
    1. 嵌入式模式 (embedded)
    2. 客户端模式 (url + api_key)
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        embedded: bool = False,
        persistence_data_path: str | None = None,
        additional_headers: dict | None = None,
    ):
        """
        初始化 Weaviate 向量数据库

        Args:
            url: Weaviate 服务器 URL（客户端模式）
            api_key: API 密钥（客户端模式）
            embedded: 是否使用嵌入式模式
            persistence_data_path: 嵌入式模式的持久化路径
            additional_headers: 额外的 HTTP 头（如 OpenAI API key）
        """
        self._url = url
        self._api_key = api_key
        self._embedded = embedded
        self._persistence_data_path = persistence_data_path
        self._additional_headers = additional_headers or {}
        self._client = None
        self._is_connected = False

        logger.info("WeaviateVectorDB 适配器已初始化")

    def connect(self, **kwargs):
        """连接到 Weaviate 数据库"""
        try:
            import weaviate

            if self._embedded:
                # 嵌入式模式
                logger.info(
                    f"使用嵌入式模式连接 Weaviate: {self._persistence_data_path}"
                )
                self._client = weaviate.Client(
                    embedded_options=weaviate.embedded.EmbeddedOptions(
                        persistence_data_path=self._persistence_data_path
                    )
                )
            else:
                # 客户端模式
                logger.info(f"使用客户端模式连接 Weaviate: {self._url}")

                auth_config = None
                if self._api_key:
                    auth_config = weaviate.AuthApiKey(api_key=self._api_key)

                self._client = weaviate.Client(
                    url=self._url,
                    auth_client_secret=auth_config,
                    additional_headers=self._additional_headers,
                )

            # 测试连接
            self._client.schema.get()
            self._is_connected = True
            logger.info("WeaviateVectorDB 连接成功")

        except ImportError:
            logger.error(
                "weaviate-client 库未安装，请运行: pip install weaviate-client"
            )
            raise RuntimeError(
                "weaviate-client 库未安装。请在 requirements.txt 中添加 weaviate-client 并安装"
            )
        except Exception as e:
            logger.error(f"连接 Weaviate 失败: {e}", exc_info=True)
            self._is_connected = False
            raise

    def create_collection(self, collection_name: str, schema: dict[str, Any]):
        """创建集合（在 Weaviate 中称为 Class）"""
        self._ensure_connected()

        try:
            # Weaviate 的 Class 名称必须首字母大写
            class_name = collection_name.capitalize()

            # 定义 Class schema
            class_obj = {
                "class": class_name,
                "description": f"长期记忆存储: {collection_name}",
                "vectorizer": "none",  # 使用外部向量
                "properties": [
                    {
                        "name": "content",
                        "dataType": ["text"],
                        "description": "记忆内容",
                    },
                    {
                        "name": "personality_id",
                        "dataType": ["text"],
                        "description": "人格ID",
                    },
                    {
                        "name": "session_id",
                        "dataType": ["text"],
                        "description": "会话ID",
                    },
                    {
                        "name": "create_time",
                        "dataType": ["int"],
                        "description": "创建时间戳",
                    },
                ],
            }

            # 如果 Class 已存在，先删除
            if self._client.schema.exists(class_name):
                logger.info(f"Class '{class_name}' 已存在，将重新创建")
                self._client.schema.delete_class(class_name)

            # 创建 Class
            self._client.schema.create_class(class_obj)
            logger.info(f"集合 '{class_name}' 已创建")

        except Exception as e:
            logger.error(f"创建集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    def insert(
        self, collection_name: str, data: list[dict[str, Any]]
    ) -> VectorInsertResult:
        """插入数据"""
        self._ensure_connected()

        if not data:
            logger.warning("尝试插入空数据列表")
            return VectorInsertResult()

        try:
            class_name = collection_name.capitalize()
            current_timestamp = int(time.time())
            inserted_ids: list[str] = []

            # 批量插入
            with self._client.batch as batch:
                for item in data:
                    # 提取向量
                    embedding = item.get("embedding")
                    if not embedding:
                        logger.warning(f"数据项缺少 embedding 字段: {item}")
                        continue

                    # 构建数据对象
                    data_object = {
                        "content": item.get("content", ""),
                        "personality_id": item.get("personality_id", ""),
                        "session_id": item.get("session_id", ""),
                        "create_time": item.get("create_time", current_timestamp),
                    }

                    # 添加到批处理
                    object_id = str(uuid.uuid4())
                    batch.add_data_object(
                        data_object=data_object,
                        class_name=class_name,
                        uuid=object_id,
                        vector=embedding,
                    )
                    inserted_ids.append(object_id)

            logger.info(f"成功向集合 '{class_name}' 插入 {len(data)} 条数据")
            return VectorInsertResult(
                insert_count=len(inserted_ids),
                primary_keys=inserted_ids,
            )

        except Exception as e:
            logger.error(f"插入数据到集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    def query(
        self,
        collection_name: str,
        filters: str | None,
        output_fields: list[str] | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """根据条件查询数据"""
        self._ensure_connected()

        try:
            class_name = collection_name.capitalize()
            fields = output_fields or [
                "content",
                "personality_id",
                "session_id",
                "create_time",
            ]

            # 构建 GraphQL 查询
            query = self._client.query.get(class_name, fields).with_additional(["id"])
            if limit:
                query = query.with_limit(limit)
            if offset:
                query = query.with_offset(offset)

            # 解析并应用过滤条件
            where_filter = self._parse_filters(filters)
            if where_filter:
                query = query.with_where(where_filter)

            # 执行查询
            result = query.do()

            # 格式化结果
            formatted_results = []
            if "data" in result and "Get" in result["data"]:
                objects = result["data"]["Get"].get(class_name, [])
                for obj in objects:
                    additional = (
                        obj.pop("_additional", {}) if isinstance(obj, dict) else {}
                    )
                    item = dict(obj)
                    item["id"] = additional.get("id", "")
                    formatted_results.append(item)

            logger.info(f"从集合 '{class_name}' 查询到 {len(formatted_results)} 条结果")
            return formatted_results

        except Exception as e:
            logger.error(f"查询集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    def update(
        self,
        collection_name: str,
        record_id: str,
        data: dict[str, Any],
    ) -> VectorInsertResult:
        """使用 Weaviate 对象更新接口保留 UUID。"""
        self._ensure_connected()
        embedding = data.get("embedding")
        if not embedding:
            raise ValueError("更新 Weaviate 记录时 embedding 不能为空")

        class_name = collection_name.capitalize()
        self._client.data_object.update(
            uuid=record_id,
            class_name=class_name,
            data_object={
                "content": data.get("content", ""),
                "personality_id": data.get("personality_id", ""),
                "session_id": data.get("session_id", ""),
                "create_time": data.get("create_time", int(time.time())),
            },
            vector=embedding,
        )
        return VectorInsertResult(insert_count=1, primary_keys=[record_id])

    def get_by_id(
        self,
        collection_name: str,
        record_id: str,
        output_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """通过 Weaviate UUID 直接读取记录。"""
        self._ensure_connected()
        result = self._client.data_object.get_by_id(
            uuid=record_id,
            class_name=collection_name.capitalize(),
            with_vector=False,
        )
        if not result:
            return None
        return {
            "id": result.get("id", record_id),
            **(result.get("properties") or {}),
        }

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: str | None = None,
        search_params: dict[str, Any] | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """执行向量相似性搜索"""
        self._ensure_connected()

        try:
            class_name = collection_name.capitalize()

            # 构建查询
            query = (
                self._client.query.get(
                    class_name,
                    ["content", "personality_id", "session_id", "create_time"],
                )
                .with_near_vector({"vector": query_vector})
                .with_limit(top_k)
                .with_additional(["distance", "id"])
            )

            # 应用过滤条件
            if filters:
                where_filter = self._parse_filters(filters)
                if where_filter:
                    query = query.with_where(where_filter)

            # 执行搜索
            result = query.do()

            # 格式化结果
            formatted_results = []
            if "data" in result and "Get" in result["data"]:
                objects = result["data"]["Get"].get(class_name, [])
                for obj in objects:
                    additional = obj.get("_additional", {})
                    distance = additional.get("distance", 0.0)

                    result_item = {
                        "id": additional.get("id", ""),
                        "_distance": distance,
                        "_score": 1.0 - distance,
                        "distance": distance,
                        "score": 1.0 - distance,  # 转换为分数
                        "content": obj.get("content", ""),
                        "personality_id": obj.get("personality_id", ""),
                        "session_id": obj.get("session_id", ""),
                        "create_time": obj.get("create_time", 0),
                    }
                    formatted_results.append(result_item)

            logger.info(f"从集合 '{class_name}' 搜索到 {len(formatted_results)} 条结果")
            return formatted_results

        except Exception as e:
            logger.error(f"搜索集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    def close(self):
        """关闭数据库连接"""
        # Weaviate 客户端不需要显式关闭
        self._is_connected = False
        logger.info("WeaviateVectorDB 连接已关闭")

    def list_collections(self) -> list[str]:
        """获取所有集合名称"""
        self._ensure_connected()

        try:
            schema = self._client.schema.get()
            classes = schema.get("classes", [])
            collection_names = [c["class"].lower() for c in classes]
            logger.info(f"获取到 {len(collection_names)} 个集合")
            return collection_names

        except Exception as e:
            logger.error(f"获取集合列表失败: {e}", exc_info=True)
            raise

    def get_loaded_collections(self) -> list[str]:
        """获取已加载的集合（Weaviate 中所有集合都是已加载的）"""
        return self.list_collections()

    def get_latest_memory(
        self, collection_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取最新的记忆"""
        self._ensure_connected()

        try:
            class_name = collection_name.capitalize()

            # 查询并按时间排序
            result = (
                self._client.query.get(
                    class_name,
                    ["content", "personality_id", "session_id", "create_time"],
                )
                .with_limit(limit)
                .with_sort([{"path": ["create_time"], "order": "desc"}])
                .do()
            )

            # 格式化结果
            formatted_results = []
            if "data" in result and "Get" in result["data"]:
                objects = result["data"]["Get"].get(class_name, [])
                formatted_results = objects

            return formatted_results

        except Exception as e:
            logger.error(f"获取最新记忆失败: {e}", exc_info=True)
            raise

    def delete(self, collection_name: str, expr: str) -> VectorDeleteResult:
        """根据条件删除数据"""
        self._ensure_connected()

        try:
            class_name = collection_name.capitalize()

            direct_id = self._extract_direct_id(expr)
            if direct_id:
                self._client.data_object.delete(
                    uuid=direct_id,
                    class_name=class_name,
                )
                logger.info(f"从集合 '{class_name}' 删除 ID 为 '{direct_id}' 的记录")
                return VectorDeleteResult(delete_count=1)

            # 解析删除条件
            where_filter = self._parse_filters(expr)

            if where_filter:
                # 使用 batch delete
                self._client.batch.delete_objects(
                    class_name=class_name,
                    where=where_filter,
                )
                logger.info(f"从集合 '{class_name}' 删除匹配条件的记录")
                return VectorDeleteResult(delete_count=None)
            else:
                logger.warning(f"无法解析删除条件: {expr}")
                return VectorDeleteResult(delete_count=0)

        except Exception as e:
            logger.error(f"删除记录失败: {e}", exc_info=True)
            raise

    @staticmethod
    def _extract_direct_id(expr: str) -> str | None:
        """解析 id/memory_id 等值表达式，映射到 Weaviate 对象 UUID。"""
        import re

        if not isinstance(expr, str):
            return None
        match = re.fullmatch(
            r'\s*(?:id|memory_id)\s*==\s*(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z0-9_.:-]+))\s*',
            expr,
        )
        if not match:
            return None
        return next((group for group in match.groups() if group), None)

    def drop_collection(self, collection_name: str) -> bool:
        """删除集合"""
        self._ensure_connected()

        try:
            class_name = collection_name.capitalize()
            self._client.schema.delete_class(class_name)
            logger.info(f"成功删除集合 '{class_name}'")
            return True

        except Exception as e:
            logger.error(f"删除集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    # --- 私有辅助方法 ---

    def _ensure_connected(self):
        """确保已连接"""
        if not self._is_connected or not self._client:
            logger.warning("Weaviate 未连接，尝试重新连接...")
            self.connect()

    def _parse_filters(self, filters: str) -> dict | None:
        """
        解析 Milvus 风格的过滤条件为 Weaviate Where 条件

        支持完整的 Milvus 表达式语法
        """
        if not filters:
            return None

        try:
            from .filter_parser import FilterParser, WeaviateFilterConverter

            # 解析为 AST
            ast = FilterParser.parse(filters)

            # 转换为 Weaviate 格式
            weaviate_filter = WeaviateFilterConverter.convert(ast)

            return weaviate_filter

        except Exception as e:
            logger.warning(f"无法解析过滤条件 '{filters}': {e}")
            return None

    def __enter__(self):
        """上下文管理器支持"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器支持"""
        self.close()
