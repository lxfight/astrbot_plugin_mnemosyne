"""
Chroma 向量数据库适配器
实现 VectorDatabase 接口，提供统一的 Chroma 数据库操作
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from astrbot.core.log import LogManager

from ..vector_db_base import VectorDatabase, VectorDeleteResult, VectorInsertResult

logger = LogManager.GetLogger(log_name="Mnemosyne ChromaAdapter")

chromadb = None


def _load_chromadb():
    """Lazy-load Chroma so importing this adapter does not require chromadb."""
    global chromadb

    if chromadb is not None:
        return chromadb

    try:
        import chromadb as chromadb_module
    except ImportError as exc:
        logger.error("chromadb 库未安装，请运行: pip install chromadb")
        raise RuntimeError(
            "chromadb 库未安装。请在 requirements.txt 中添加 chromadb 并安装"
        ) from exc

    chromadb = chromadb_module
    return chromadb_module


def _chroma_settings():
    try:
        from chromadb.config import Settings

        return Settings(anonymized_telemetry=False)
    except Exception:
        return None


def _quiet_chroma_telemetry_logs():
    logging.getLogger("chromadb.telemetry.product.posthog").disabled = True


class ChromaVectorDB(VectorDatabase):
    """
    Chroma 向量数据库适配器

    支持两种模式：
    1. 本地持久化模式 (persist_directory)
    2. 客户端模式 (host + port)
    """

    def __init__(
        self,
        persist_directory: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ):
        """
        初始化 Chroma 向量数据库

        Args:
            persist_directory: 本地持久化目录（本地模式）
            host: Chroma 服务器地址（客户端模式）
            port: Chroma 服务器端口（客户端模式）
        """
        self._persist_directory = persist_directory
        self._host = host
        self._port = port
        self._client = None
        self._is_connected = False

        logger.info("ChromaVectorDB 适配器已初始化")

    def connect(self, **kwargs):
        """连接到 Chroma 数据库"""
        try:
            os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
            _quiet_chroma_telemetry_logs()
            chromadb_module = _load_chromadb()
            settings = _chroma_settings()

            if self._host:
                # 客户端模式
                logger.info(f"使用客户端模式连接 Chroma: {self._host}:{self._port}")
                client_kwargs = {"host": self._host, "port": self._port}
                if settings is not None:
                    client_kwargs["settings"] = settings
                self._client = chromadb_module.HttpClient(**client_kwargs)
            else:
                # 本地持久化模式
                logger.info(f"使用持久化模式连接 Chroma: {self._persist_directory}")

                # 确保目录存在
                if self._persist_directory:
                    Path(self._persist_directory).mkdir(parents=True, exist_ok=True)

                client_kwargs = {"path": self._persist_directory}
                if settings is not None:
                    client_kwargs["settings"] = settings
                self._client = chromadb_module.PersistentClient(**client_kwargs)

            self._is_connected = True
            logger.info("ChromaVectorDB 连接成功")

        except Exception as e:
            logger.error(f"连接 Chroma 失败: {e}", exc_info=True)
            self._is_connected = False
            raise

    def create_collection(self, collection_name: str, schema: dict[str, Any]):
        """
        创建集合

        Args:
            collection_name: 集合名称
            schema: 集合 schema（Chroma 不需要预定义 schema，此参数仅用于兼容）
        """
        self._ensure_connected()

        try:
            # Chroma 自动管理 schema，直接创建或获取集合
            self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "l2"},  # 使用 L2 距离
            )
            logger.info(f"集合 '{collection_name}' 已创建或获取")

        except Exception as e:
            logger.error(f"创建集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    def insert(
        self, collection_name: str, data: list[dict[str, Any]]
    ) -> VectorInsertResult:
        """
        插入数据

        Args:
            collection_name: 集合名称
            data: 数据列表
        """
        self._ensure_connected()

        if not data:
            logger.warning("尝试插入空数据列表")
            return VectorInsertResult()

        try:
            collection = self._client.get_collection(name=collection_name)

            # 准备数据
            ids = []
            embeddings = []
            metadatas = []
            documents = []

            current_timestamp = int(time.time())

            for item in data:
                # 提取向量
                embedding = item.get("embedding")
                if not embedding:
                    logger.warning(f"数据项缺少 embedding 字段: {item}")
                    continue
                embeddings.append(embedding)

                # 生成 ID（使用时间戳 + 随机数）
                import uuid

                item_id = f"{current_timestamp}_{uuid.uuid4().hex[:8]}"
                ids.append(item_id)

                # 提取文档内容
                content = item.get("content", "")
                documents.append(content)

                # 提取元数据
                metadata = {
                    "personality_id": item.get("personality_id", ""),
                    "session_id": item.get("session_id", ""),
                    "create_time": item.get("create_time", current_timestamp),
                }
                metadatas.append(metadata)

            if not ids:
                logger.warning("没有可插入的有效 Chroma 数据")
                return VectorInsertResult()

            # 批量插入
            collection.add(
                ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
            )

            logger.info(f"成功向集合 '{collection_name}' 插入 {len(ids)} 条数据")
            return VectorInsertResult(insert_count=len(ids), primary_keys=ids)

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
        """
        根据条件查询数据

        Args:
            collection_name: 集合名称
            filters: 过滤条件（简化版，仅支持基本过滤）
            output_fields: 返回字段列表

        Returns:
            查询结果列表
        """
        self._ensure_connected()

        try:
            collection = self._client.get_collection(name=collection_name)

            # Chroma 的查询接口与 Milvus 不同
            # 这里需要根据 filters 构建 where 条件
            where = self._parse_filters(filters)

            # 获取数据，避免把 None 参数传给不同版本的 Chroma 客户端。
            get_kwargs = {"include": ["metadatas", "documents"]}
            if where is not None:
                get_kwargs["where"] = where
            if limit is not None:
                get_kwargs["limit"] = limit
            if offset is not None:
                get_kwargs["offset"] = offset
            results = collection.get(**get_kwargs)

            # 格式化结果
            formatted_results = []
            for i in range(len(results["ids"])):
                result = {
                    "id": results["ids"][i],
                    "content": results["documents"][i]
                    if "documents" in results
                    else "",
                }

                # 添加元数据
                if "metadatas" in results and i < len(results["metadatas"]):
                    result.update(results["metadatas"][i])

                formatted_results.append(result)

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
        """使用 Chroma 原生 update 保留文档 ID。"""
        self._ensure_connected()
        embedding = data.get("embedding")
        if not embedding:
            raise ValueError("更新 Chroma 记录时 embedding 不能为空")

        collection = self._client.get_collection(name=collection_name)
        collection.update(
            ids=[record_id],
            embeddings=[embedding],
            documents=[data.get("content", "")],
            metadatas=[
                {
                    "personality_id": data.get("personality_id", ""),
                    "session_id": data.get("session_id", ""),
                    "create_time": data.get("create_time", int(time.time())),
                }
            ],
        )
        return VectorInsertResult(insert_count=1, primary_keys=[record_id])

    def get_by_id(
        self,
        collection_name: str,
        record_id: str,
        output_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """通过 Chroma 文档 ID 直接读取记录。"""
        self._ensure_connected()
        collection = self._client.get_collection(name=collection_name)
        result = collection.get(
            ids=[record_id],
            include=["metadatas", "documents"],
        )
        if not result.get("ids"):
            return None
        record = {
            "id": result["ids"][0],
            "content": (result.get("documents") or [""])[0],
        }
        metadata = (result.get("metadatas") or [{}])[0] or {}
        record.update(metadata)
        return record

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
        执行向量相似性搜索

        Args:
            collection_name: 集合名称
            query_vector: 查询向量
            top_k: 返回结果数量
            filters: 过滤条件

        Returns:
            搜索结果列表
        """
        self._ensure_connected()

        try:
            collection = self._client.get_collection(name=collection_name)

            # 构建查询参数
            where = self._parse_filters(filters) if filters else None

            # 执行搜索
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=where,
                include=["metadatas", "documents", "distances"],
            )

            # 格式化结果
            formatted_results = []
            if results and results["ids"]:
                for i in range(len(results["ids"][0])):
                    distance = (
                        results["distances"][0][i] if "distances" in results else 0.0
                    )
                    score = 1.0 / (1.0 + distance)  # 转换为分数

                    result = {
                        "id": results["ids"][0][i],
                        "_distance": distance,
                        "_score": score,
                        "distance": distance,
                        "score": score,
                        "content": results["documents"][0][i]
                        if "documents" in results
                        else "",
                    }

                    # 添加元数据
                    if "metadatas" in results and i < len(results["metadatas"][0]):
                        result.update(results["metadatas"][0][i])

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
        # Chroma 客户端不需要显式关闭
        self._is_connected = False
        logger.info("ChromaVectorDB 连接已关闭")

    def list_collections(self) -> list[str]:
        """获取所有集合名称"""
        self._ensure_connected()

        try:
            collections = self._client.list_collections()
            collection_names = [c.name for c in collections]
            logger.info(f"获取到 {len(collection_names)} 个集合")
            return collection_names

        except Exception as e:
            logger.error(f"获取集合列表失败: {e}", exc_info=True)
            raise

    def get_loaded_collections(self) -> list[str]:
        """获取已加载的集合（Chroma 中所有集合都是已加载的）"""
        return self.list_collections()

    def get_latest_memory(
        self, collection_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        获取最新的记忆

        Args:
            collection_name: 集合名称
            limit: 返回数量

        Returns:
            最新记忆列表
        """
        self._ensure_connected()

        try:
            collection = self._client.get_collection(name=collection_name)

            # 获取所有数据
            results = collection.get(include=["metadatas", "documents"], limit=limit)

            # 格式化并按时间排序
            formatted_results = []
            for i in range(len(results["ids"])):
                result = {
                    "id": results["ids"][i],
                    "content": results["documents"][i]
                    if "documents" in results
                    else "",
                }

                if "metadatas" in results and i < len(results["metadatas"]):
                    result.update(results["metadatas"][i])

                formatted_results.append(result)

            # 按 create_time 降序排序
            formatted_results.sort(key=lambda x: x.get("create_time", 0), reverse=True)

            return formatted_results[:limit]

        except Exception as e:
            logger.error(f"获取最新记忆失败: {e}", exc_info=True)
            raise

    def delete(self, collection_name: str, expr: str) -> VectorDeleteResult:
        """
        根据条件删除数据

        Args:
            collection_name: 集合名称
            expr: 删除条件表达式
        """
        self._ensure_connected()

        try:
            collection = self._client.get_collection(name=collection_name)

            direct_id = self._extract_direct_id(expr)
            if direct_id:
                collection.delete(ids=[direct_id])
                logger.info(
                    f"从集合 '{collection_name}' 删除 ID 为 '{direct_id}' 的记录"
                )
                return VectorDeleteResult(delete_count=1)

            # 解析删除条件
            where = self._parse_filters(expr)

            # 先查询出要删除的 ID
            results = collection.get(where=where, include=[])
            ids_to_delete = results["ids"]

            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.info(
                    f"从集合 '{collection_name}' 删除了 {len(ids_to_delete)} 条记录"
                )
                return VectorDeleteResult(delete_count=len(ids_to_delete))
            else:
                logger.info(f"集合 '{collection_name}' 中没有匹配条件的记录")
                return VectorDeleteResult(delete_count=0)

        except Exception as e:
            logger.error(f"删除记录失败: {e}", exc_info=True)
            raise

    @staticmethod
    def _extract_direct_id(expr: str) -> str | None:
        """解析 id/memory_id 等值表达式，映射到 Chroma 文档 ID。"""
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
            self._client.delete_collection(name=collection_name)
            logger.info(f"成功删除集合 '{collection_name}'")
            return True

        except Exception as e:
            logger.error(f"删除集合 '{collection_name}' 失败: {e}", exc_info=True)
            raise

    # --- 私有辅助方法 ---

    def _ensure_connected(self):
        """确保已连接"""
        if not self._is_connected or not self._client:
            logger.warning("Chroma 未连接，尝试重新连接...")
            self.connect()

    def _parse_filters(self, filters: str) -> dict[str, Any] | None:
        """
        解析 Milvus 风格的过滤条件为 Chroma where 条件

        支持完整的 Milvus 表达式语法
        """
        if not filters:
            return None

        try:
            from .filter_parser import ChromaFilterConverter, FilterParser

            # 解析为 AST
            ast = FilterParser.parse(filters)

            # 转换为 Chroma 格式
            chroma_filter = ChromaFilterConverter.convert(ast)

            return chroma_filter

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
