"""
Qdrant 向量数据库适配器
实现 VectorDatabase 接口，提供统一的 Qdrant 数据库操作
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from astrbot.core.log import LogManager

from ..vector_db_base import VectorDatabase, VectorDeleteResult, VectorInsertResult

logger = LogManager.GetLogger(log_name="Mnemosyne QdrantAdapter")


class QdrantVectorDB(VectorDatabase):
    """
    Qdrant 向量数据库适配器

    支持两种模式：
    1. 本地持久化模式 (path)
    2. 客户端模式 (url)
    """

    def __init__(
        self,
        path: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        collection_config: dict | None = None,
    ):
        """
        初始化 Qdrant 向量数据库

        Args:
            path: 本地持久化路径（本地模式）
            url: Qdrant 服务器 URL（客户端模式）
            api_key: API 密钥（客户端模式）
            collection_config: 集合配置（向量大小、距离度量等）
        """
        self._path = path
        self._url = url
        self._api_key = api_key
        self._collection_config = collection_config or {}
        self._client = None
        self._is_connected = False

        logger.info("QdrantVectorDB 适配器已初始化")

    def connect(self, **kwargs):
        """连接到 Qdrant 数据库"""
        try:
            from qdrant_client import QdrantClient

            if self._url:
                # 客户端模式
                logger.info(f"使用客户端模式连接 Qdrant: {self._url}")
                self._client = QdrantClient(
                    url=self._url,
                    api_key=self._api_key,
                )
            else:
                # 本地持久化模式
                logger.info(f"使用持久化模式连接 Qdrant: {self._path}")

                # 确保目录存在
                if self._path:
                    Path(self._path).mkdir(parents=True, exist_ok=True)

                self._client = QdrantClient(path=self._path)

            self._is_connected = True
            logger.info("QdrantVectorDB 连接成功")

        except ImportError:
            logger.error("qdrant-client 库未安装，请运行: pip install qdrant-client")
            raise RuntimeError(
                "qdrant-client 库未安装。请在 requirements.txt 中添加 qdrant-client 并安装"
            )
        except Exception as e:
            logger.error(f"连接 Qdrant 失败: {e}", exc_info=True)
            self._is_connected = False
            raise

    def create_collection(self, collection_name: str, schema: dict[str, Any]):
        """创建集合"""
        self._ensure_connected()

        try:
            from qdrant_client.models import Distance, VectorParams

            # 从 schema 中提取向量维度
            vector_dim = self._collection_config.get("vector_size", 768)
            for field in schema.get("fields", []):
                if field.get("name") == "embedding" and "dim" in field:
                    vector_dim = field["dim"]
                    break

            # 确定距离度量类型
            distance_metric = self._collection_config.get("distance", "Cosine")
            distance_map = {
                "Cosine": Distance.COSINE,
                "Euclidean": Distance.EUCLID,
                "Dot": Distance.DOT,
            }
            distance = distance_map.get(distance_metric, Distance.COSINE)

            # 创建集合
            self._client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_dim, distance=distance),
            )

            logger.info(
                f"集合 '{collection_name}' 已创建（维度: {vector_dim}, 距离: {distance_metric}）"
            )

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
            from qdrant_client.models import PointStruct

            points = []
            current_timestamp = int(time.time())

            for idx, item in enumerate(data):
                # 提取向量
                embedding = item.get("embedding")
                if not embedding:
                    logger.warning(f"数据项缺少 embedding 字段: {item}")
                    continue

                # Qdrant point ID 使用 UUID，避免字符串格式不被接受。
                point_id = str(uuid.uuid4())

                # 构建 payload
                payload = {
                    "content": item.get("content", ""),
                    "personality_id": item.get("personality_id", ""),
                    "session_id": item.get("session_id", ""),
                    "create_time": item.get("create_time", current_timestamp),
                }

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload,
                    )
                )

            if not points:
                logger.warning("没有可插入的有效 Qdrant 数据")
                return VectorInsertResult()

            # 批量插入
            self._client.upsert(
                collection_name=collection_name,
                points=points,
            )

            logger.info(f"成功向集合 '{collection_name}' 插入 {len(points)} 条数据")
            return VectorInsertResult(
                insert_count=len(points),
                primary_keys=[point.id for point in points],
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
            # 解析过滤条件
            qdrant_filter = self._parse_filters(filters)

            fetch_limit = (limit or 100) + (offset or 0)
            # Qdrant scroll 的 offset 是游标，不是整数分页偏移；这里先多取再本地切片。
            results = self._client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                limit=fetch_limit,
                with_payload=True,
                with_vectors=False,
            )

            # 格式化结果
            formatted_results = []
            for point in results[0]:  # results 是 (points, next_offset) 元组
                result = {
                    "id": point.id,
                    **point.payload,
                }
                formatted_results.append(result)

            if offset:
                formatted_results = formatted_results[offset:]
            if limit is not None:
                formatted_results = formatted_results[:limit]

            logger.info(
                f"从集合 '{collection_name}' 查询到 {len(formatted_results)} 条结果"
            )
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
        """使用 Qdrant upsert 原子替换并保留 point ID。"""
        self._ensure_connected()
        embedding = data.get("embedding")
        if not embedding:
            raise ValueError("更新 Qdrant 记录时 embedding 不能为空")

        from qdrant_client.models import PointStruct

        point = PointStruct(
            id=record_id,
            vector=embedding,
            payload={
                "content": data.get("content", ""),
                "personality_id": data.get("personality_id", ""),
                "session_id": data.get("session_id", ""),
                "create_time": data.get("create_time", int(time.time())),
            },
        )
        self._client.upsert(collection_name=collection_name, points=[point])
        return VectorInsertResult(insert_count=1, primary_keys=[record_id])

    def get_by_id(
        self,
        collection_name: str,
        record_id: str,
        output_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """通过 Qdrant point ID 直接读取记录。"""
        self._ensure_connected()
        points = self._client.retrieve(
            collection_name=collection_name,
            ids=[record_id],
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return None
        return {"id": points[0].id, **(points[0].payload or {})}

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
            # 解析过滤条件
            qdrant_filter = self._parse_filters(filters) if filters else None

            # 执行搜索
            results = self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
            )

            # 格式化结果
            formatted_results = []
            for hit in results:
                result = {
                    "id": hit.id,
                    "_score": hit.score,
                    "_distance": 1.0 - hit.score,
                    "score": hit.score,
                    "distance": 1.0 - hit.score,  # 转换为距离
                    **hit.payload,
                }
                formatted_results.append(result)

            logger.info(
                f"从集合 '{collection_name}' 搜索到 {len(formatted_results)} 条结果"
            )
            return formatted_results

        except Exception as e:
            logger.error(f"搜索集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    def close(self):
        """关闭数据库连接"""
        if self._client:
            self._client.close()
        self._is_connected = False
        logger.info("QdrantVectorDB 连接已关闭")

    def list_collections(self) -> list[str]:
        """获取所有集合名称"""
        self._ensure_connected()

        try:
            collections = self._client.get_collections()
            collection_names = [c.name for c in collections.collections]
            logger.info(f"获取到 {len(collection_names)} 个集合")
            return collection_names

        except Exception as e:
            logger.error(f"获取集合列表失败: {e}", exc_info=True)
            raise

    def get_loaded_collections(self) -> list[str]:
        """获取已加载的集合（Qdrant 中所有集合都是已加载的）"""
        return self.list_collections()

    def get_latest_memory(
        self, collection_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取最新的记忆"""
        self._ensure_connected()

        try:
            # 使用 scroll 获取数据并按时间排序
            results = self._client.scroll(
                collection_name=collection_name,
                limit=limit * 2,  # 获取更多以便排序
                with_payload=True,
                with_vectors=False,
            )

            # 格式化结果
            formatted_results = []
            for point in results[0]:
                result = {
                    "id": point.id,
                    **point.payload,
                }
                formatted_results.append(result)

            # 按 create_time 降序排序
            formatted_results.sort(key=lambda x: x.get("create_time", 0), reverse=True)

            return formatted_results[:limit]

        except Exception as e:
            logger.error(f"获取最新记忆失败: {e}", exc_info=True)
            raise

    def delete(self, collection_name: str, expr: str) -> VectorDeleteResult:
        """根据条件删除数据"""
        self._ensure_connected()

        try:
            from qdrant_client.models import FilterSelector

            direct_id = self._extract_direct_id(expr)
            if direct_id:
                self._client.delete(
                    collection_name=collection_name,
                    points_selector=[direct_id],
                )
                logger.info(
                    f"从集合 '{collection_name}' 删除 ID 为 '{direct_id}' 的记录"
                )
                return VectorDeleteResult(delete_count=1)

            # 解析删除条件
            qdrant_filter = self._parse_filters(expr)

            # 使用 filter 删除
            self._client.delete(
                collection_name=collection_name,
                points_selector=FilterSelector(filter=qdrant_filter),
            )

            logger.info(f"从集合 '{collection_name}' 删除匹配条件的记录")
            return VectorDeleteResult(delete_count=None)

        except Exception as e:
            logger.error(f"删除记录失败: {e}", exc_info=True)
            raise

    @staticmethod
    def _extract_direct_id(expr: str) -> str | None:
        """解析 id/memory_id 等值表达式，映射到 Qdrant point ID。"""
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
            self._client.delete_collection(collection_name=collection_name)
            logger.info(f"成功删除集合 '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"删除集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    # --- 私有辅助方法 ---

    def _ensure_connected(self):
        """确保已连接"""
        if not self._is_connected or not self._client:
            logger.warning("Qdrant 未连接，尝试重新连接...")
            self.connect()

    def _parse_filters(self, filters: str) -> Any:
        """
        解析 Milvus 风格的过滤条件为 Qdrant Filter

        支持完整的 Milvus 表达式语法
        """
        if not filters:
            return None

        try:
            from .filter_parser import FilterParser, QdrantFilterConverter

            # 解析为 AST
            ast = FilterParser.parse(filters)

            # 转换为 Qdrant 格式
            qdrant_filter = QdrantFilterConverter.convert(ast)

            return qdrant_filter

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
