# -*- coding: utf-8 -*-
"""
FAISS 向量数据库管理器
提供高效的向量相似性搜索和持久化存储功能
"""

import os
import json
import pickle
import time
import uuid
from typing import List, Dict, Any, Optional
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from astrbot.core.log import LogManager
from ..vector_db_base import VectorDatabase, VectorDatabaseType


class FaissManager(VectorDatabase):
    """
    FAISS 向量数据库管理器
    支持高效的向量相似性搜索和本地持久化存储
    """

    def __init__(
        self,
        data_path: str = "./faiss_data",
        index_type: str = "IndexFlatL2",
        nlist: int = 100,
        **kwargs,
    ):
        """
        初始化 FAISS 管理器

        Args:
            data_path: 数据存储路径
            index_type: FAISS 索引类型 (IndexFlatL2, IndexIVFFlat, IndexHNSWFlat)
            nlist: IVF 索引的聚类中心数量
            **kwargs: 其他参数
        """
        super().__init__(VectorDatabaseType.FAISS)

        if faiss is None:
            raise ImportError(
                "FAISS library not installed. Please install with: pip install faiss-cpu"
            )

        self.data_path = os.path.abspath(data_path)
        self.index_type = index_type
        self.nlist = nlist
        self.logger = LogManager.GetLogger(log_name="FaissManager")

        # 存储集合信息
        self.collections: Dict[str, Dict[str, Any]] = {}
        self.indexes: Dict[str, faiss.Index] = {} # type: ignore
        self.metadata: Dict[str, List[Dict[str, Any]]] = {}

        # 确保数据目录存在
        os.makedirs(self.data_path, exist_ok=True)

        self.logger.info(f"FAISS Manager initialized with data path: {self.data_path}")

    def connect(self, **kwargs) -> bool:
        """
        连接到 FAISS（加载已有数据）
        """
        try:
            self._load_collections_metadata()
            self._load_existing_collections()
            self._is_connected = True
            self.logger.info("Successfully connected to FAISS database")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to FAISS: {e}", exc_info=True)
            return False

    def disconnect(self) -> bool:
        """
        断开 FAISS 连接（保存数据）
        """
        try:
            self._save_all_collections()
            self._save_collections_metadata()
            self._is_connected = False
            self.logger.info("Successfully disconnected from FAISS database")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disconnect from FAISS: {e}", exc_info=True)
            return False

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._is_connected

    def create_collection(
        self, collection_name: str, schema: Dict[str, Any], **kwargs
    ) -> bool:
        """
        创建新集合

        Args:
            collection_name: 集合名称
            schema: 集合模式定义
            **kwargs: 额外参数
        """
        try:
            if collection_name in self.collections:
                self.logger.warning(f"Collection '{collection_name}' already exists")
                return True

            # 从 schema 中提取向量维度
            vector_dim = self._extract_vector_dimension(schema)
            if vector_dim is None:
                raise ValueError("Cannot determine vector dimension from schema")

            # 创建 FAISS 索引
            index = self._create_faiss_index(vector_dim)

            # 存储集合信息
            self.collections[collection_name] = {
                "schema": schema,
                "vector_dim": vector_dim,
                "created_time": time.time(),
                "record_count": 0,
            }
            self.indexes[collection_name] = index
            self.metadata[collection_name] = []

            self.logger.info(
                f"Created collection '{collection_name}' with dimension {vector_dim}"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to create collection '{collection_name}': {e}", exc_info=True
            )
            return False

    def has_collection(self, collection_name: str) -> bool:
        """检查集合是否存在"""
        return collection_name in self.collections

    def drop_collection(self, collection_name: str) -> bool:
        """删除集合"""
        try:
            if collection_name not in self.collections:
                self.logger.warning(f"Collection '{collection_name}' does not exist")
                return True

            # 删除内存中的数据
            del self.collections[collection_name]
            del self.indexes[collection_name]
            del self.metadata[collection_name]

            # 删除磁盘文件
            collection_dir = os.path.join(self.data_path, collection_name)
            if os.path.exists(collection_dir):
                import shutil

                shutil.rmtree(collection_dir)

            self.logger.info(f"Dropped collection '{collection_name}'")
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to drop collection '{collection_name}': {e}", exc_info=True
            )
            return False

    def list_collections(self) -> List[str]:
        """获取所有集合名称"""
        return list(self.collections.keys())

    def insert(
        self, collection_name: str, data: List[Dict[str, Any]], **kwargs
    ) -> bool:
        """
        插入数据到集合

        Args:
            collection_name: 集合名称
            data: 要插入的数据列表
            **kwargs: 额外参数
        """
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Collection '{collection_name}' does not exist")

            if not data:
                return True

            # 提取向量和元数据
            vectors = []
            metadata_records = []

            for record in data:
                # 提取向量字段
                vector = self._extract_vector_from_record(record)
                if vector is None:
                    continue

                vectors.append(vector)

                # 生成唯一ID（如果没有提供）
                if "memory_id" not in record:
                    record["memory_id"] = int(str(uuid.uuid4().int)[:18])

                metadata_records.append(record)

            if not vectors:
                self.logger.warning("No valid vectors found in data")
                return False

            # 转换为 numpy 数组
            vectors_array = np.array(vectors, dtype=np.float32)

            # 添加到 FAISS 索引
            index = self.indexes[collection_name]
            index.add(vectors_array)

            # 存储元数据
            self.metadata[collection_name].extend(metadata_records)

            # 更新记录数
            self.collections[collection_name]["record_count"] += len(vectors)

            self.logger.info(
                f"Inserted {len(vectors)} records into collection '{collection_name}'"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to insert data into collection '{collection_name}': {e}",
                exc_info=True,
            )
            return False

    def search(
        self,
        collection_name: str,
        query_vectors: List[List[float]],
        top_k: int,
        filters: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
        **kwargs,
    ) -> List[List[Dict[str, Any]]]:
        """
        执行向量相似性搜索

        Args:
            collection_name: 集合名称
            query_vectors: 查询向量列表
            top_k: 返回的最相似结果数量
            filters: 过滤条件（简单的字符串表达式）
            output_fields: 返回的字段列表
            **kwargs: 额外参数
        """
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Collection '{collection_name}' does not exist")

            if not query_vectors:
                return []

            # 转换查询向量为 numpy 数组
            query_array = np.array(query_vectors, dtype=np.float32)

            # 执行 FAISS 搜索
            index = self.indexes[collection_name]
            distances, indices = index.search(query_array, top_k)

            # 获取元数据
            collection_metadata = self.metadata[collection_name]

            results = []
            for i, (query_distances, query_indices) in enumerate(
                zip(distances, indices)
            ):
                query_results = []
                for distance, idx in zip(query_distances, query_indices):
                    if idx == -1:  # FAISS 返回 -1 表示无效结果
                        continue

                    if idx >= len(collection_metadata):
                        continue

                    record = collection_metadata[idx].copy()
                    record["distance"] = float(distance)

                    # 应用过滤器
                    if filters and not self._apply_filter(record, filters):
                        continue

                    # 选择输出字段
                    if output_fields:
                        filtered_record = {
                            field: record.get(field) for field in output_fields
                        }
                        filtered_record["distance"] = record["distance"]
                        record = filtered_record

                    query_results.append(record)

                results.append(query_results)

            self.logger.debug(
                f"Search in collection '{collection_name}' returned {len(results)} result sets"
            )
            return results

        except Exception as e:
            self.logger.error(
                f"Failed to search in collection '{collection_name}': {e}",
                exc_info=True,
            )
            return []

    def query(
        self,
        collection_name: str,
        filters: str,
        output_fields: List[str],
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        根据条件查询数据

        Args:
            collection_name: 集合名称
            filters: 查询条件表达式
            output_fields: 返回的字段列表
            limit: 限制返回数量
            **kwargs: 额外参数
        """
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Collection '{collection_name}' does not exist")

            collection_metadata = self.metadata[collection_name]
            results = []

            for record in collection_metadata:
                if self._apply_filter(record, filters):
                    # 选择输出字段
                    if output_fields:
                        filtered_record = {
                            field: record.get(field) for field in output_fields
                        }
                    else:
                        filtered_record = record.copy()

                    results.append(filtered_record)

                    if limit and len(results) >= limit:
                        break

            self.logger.debug(
                f"Query in collection '{collection_name}' returned {len(results)} records"
            )
            return results

        except Exception as e:
            self.logger.error(
                f"Failed to query collection '{collection_name}': {e}", exc_info=True
            )
            return []

    def delete(self, collection_name: str, filters: str, **kwargs) -> bool:
        """
        根据条件删除记录
        注意：FAISS 不支持直接删除，这里通过重建索引实现
        """
        try:
            if collection_name not in self.collections:
                raise ValueError(f"Collection '{collection_name}' does not exist")

            collection_metadata = self.metadata[collection_name]

            # 找到要保留的记录
            remaining_records = []
            deleted_count = 0

            for record in collection_metadata:
                if not self._apply_filter(record, filters):
                    remaining_records.append(record)
                else:
                    deleted_count += 1

            if deleted_count == 0:
                self.logger.info(
                    f"No records matched deletion criteria in collection '{collection_name}'"
                )
                return True

            # 重建索引和元数据
            self.metadata[collection_name] = remaining_records

            # 重建 FAISS 索引
            if remaining_records:
                vectors = []
                for record in remaining_records:
                    vector = self._extract_vector_from_record(record)
                    if vector is not None:
                        vectors.append(vector)

                if vectors:
                    vector_dim = self.collections[collection_name]["vector_dim"]
                    new_index = self._create_faiss_index(vector_dim)
                    vectors_array = np.array(vectors, dtype=np.float32)
                    new_index.add(vectors_array)
                    self.indexes[collection_name] = new_index
                else:
                    # 如果没有向量，创建空索引
                    vector_dim = self.collections[collection_name]["vector_dim"]
                    self.indexes[collection_name] = self._create_faiss_index(vector_dim)
            else:
                # 如果没有剩余记录，创建空索引
                vector_dim = self.collections[collection_name]["vector_dim"]
                self.indexes[collection_name] = self._create_faiss_index(vector_dim)

            # 更新记录数
            self.collections[collection_name]["record_count"] = len(remaining_records)

            self.logger.info(
                f"Deleted {deleted_count} records from collection '{collection_name}'"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to delete from collection '{collection_name}': {e}",
                exc_info=True,
            )
            return False

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """获取集合统计信息"""
        if collection_name not in self.collections:
            return {}

        collection_info = self.collections[collection_name]
        index = self.indexes[collection_name]

        return {
            "name": collection_name,
            "record_count": collection_info["record_count"],
            "vector_dim": collection_info["vector_dim"],
            "index_type": self.index_type,
            "created_time": collection_info["created_time"],
            "index_size": index.ntotal if hasattr(index, "ntotal") else 0,
        }

    # Helper methods
    def _extract_vector_dimension(self, schema: Dict[str, Any]) -> Optional[int]:
        """从 schema 中提取向量维度"""
        try:
            # 支持 Milvus 风格的 schema
            if "fields" in schema:
                for field in schema["fields"]:
                    if (
                        field.get("name") == "embedding"
                        and field.get("dtype") == "FLOAT_VECTOR"
                    ):
                        return field.get("dim")

            # 支持简单的配置格式
            if "vector_dim" in schema:
                return schema["vector_dim"]

            if "embedding_dim" in schema:
                return schema["embedding_dim"]

            # 默认维度
            return 1024

        except Exception as e:
            self.logger.error(f"Failed to extract vector dimension from schema: {e}")
            return None

    def _create_faiss_index(self, vector_dim: int):
        """创建 FAISS 索引"""
        try:
            if self.index_type == "IndexFlatL2":
                return faiss.IndexFlatL2(vector_dim)
            elif self.index_type == "IndexFlatIP":
                return faiss.IndexFlatIP(vector_dim)
            elif self.index_type == "IndexIVFFlat":
                quantizer = faiss.IndexFlatL2(vector_dim)
                return faiss.IndexIVFFlat(quantizer, vector_dim, self.nlist)
            elif self.index_type == "IndexHNSWFlat":
                return faiss.IndexHNSWFlat(vector_dim, 32)
            else:
                self.logger.warning(
                    f"Unknown index type '{self.index_type}', using IndexFlatL2"
                )
                return faiss.IndexFlatL2(vector_dim)

        except Exception as e:
            self.logger.error(f"Failed to create FAISS index: {e}")
            return faiss.IndexFlatL2(vector_dim)

    def _extract_vector_from_record(
        self, record: Dict[str, Any]
    ) -> Optional[List[float]]:
        """从记录中提取向量"""
        try:
            # 尝试不同的向量字段名
            for field_name in ["embedding", "vector", "embeddings"]:
                if field_name in record:
                    vector = record[field_name]
                    if isinstance(vector, (list, np.ndarray)):
                        return (
                            list(vector) if isinstance(vector, np.ndarray) else vector
                        )

            return None

        except Exception as e:
            self.logger.error(f"Failed to extract vector from record: {e}")
            return None

    def _apply_filter(self, record: Dict[str, Any], filters: str) -> bool:
        """应用简单的过滤条件"""
        try:
            if not filters or filters.strip() == "":
                return True

            # 简单的过滤器实现，支持基本的等式和比较
            # 例如: 'session_id == "session_1"' 或 'memory_id > 0'

            # 移除多余的空格
            filters = filters.strip()

            # 支持 AND 连接的多个条件
            conditions = [cond.strip() for cond in filters.split(" and ")]

            for condition in conditions:
                if not self._evaluate_condition(record, condition):
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Failed to apply filter '{filters}': {e}")
            return True  # 过滤失败时默认包含记录

    def _evaluate_condition(self, record: Dict[str, Any], condition: str) -> bool:
        """评估单个条件"""
        try:
            # 支持的操作符
            operators = ["==", "!=", ">=", "<=", ">", "<", "in"]

            for op in operators:
                if op in condition:
                    parts = condition.split(op, 1)
                    if len(parts) != 2:
                        continue

                    field_name = parts[0].strip()
                    value_str = parts[1].strip().strip("\"'")

                    if field_name not in record:
                        return False

                    record_value = record[field_name]

                    # 类型转换
                    try:
                        if isinstance(record_value, (int, float)):
                            compare_value = float(value_str)
                        else:
                            compare_value = value_str
                    except ValueError:
                        compare_value = value_str

                    # 执行比较
                    if op == "==":
                        return record_value == compare_value
                    elif op == "!=":
                        return record_value != compare_value
                    elif op == ">":
                        return record_value > compare_value
                    elif op == ">=":
                        return record_value >= compare_value
                    elif op == "<":
                        return record_value < compare_value
                    elif op == "<=":
                        return record_value <= compare_value
                    elif op == "in":
                        # 简单的 in 操作，支持列表格式
                        if value_str.startswith("[") and value_str.endswith("]"):
                            value_list = [
                                v.strip().strip("\"'")
                                for v in value_str[1:-1].split(",")
                            ]
                            return str(record_value) in value_list
                        else:
                            return value_str in str(record_value)

            return True

        except Exception as e:
            self.logger.error(f"Failed to evaluate condition '{condition}': {e}")
            return True

    def _save_all_collections(self):
        """保存所有集合到磁盘"""
        try:
            for collection_name in self.collections:
                self._save_collection(collection_name)
        except Exception as e:
            self.logger.error(f"Failed to save collections: {e}", exc_info=True)

    def _save_collection(self, collection_name: str):
        """保存单个集合到磁盘"""
        try:
            collection_dir = os.path.join(self.data_path, collection_name)
            os.makedirs(collection_dir, exist_ok=True)

            # 保存 FAISS 索引
            index_path = os.path.join(collection_dir, "index.faiss")
            faiss.write_index(self.indexes[collection_name], index_path)

            # 保存元数据
            metadata_path = os.path.join(collection_dir, "metadata.pkl")
            with open(metadata_path, "wb") as f:
                pickle.dump(self.metadata[collection_name], f)

            # 保存集合信息
            info_path = os.path.join(collection_dir, "info.json")
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(
                    self.collections[collection_name], f, ensure_ascii=False, indent=2
                )

            self.logger.debug(f"Saved collection '{collection_name}' to disk")

        except Exception as e:
            self.logger.error(
                f"Failed to save collection '{collection_name}': {e}", exc_info=True
            )

    def _load_existing_collections(self):
        """加载已有的集合"""
        try:
            if not os.path.exists(self.data_path):
                return

            for item in os.listdir(self.data_path):
                collection_dir = os.path.join(self.data_path, item)
                if os.path.isdir(collection_dir):
                    self._load_collection(item)

        except Exception as e:
            self.logger.error(
                f"Failed to load existing collections: {e}", exc_info=True
            )

    def _load_collection(self, collection_name: str):
        """加载单个集合"""
        try:
            collection_dir = os.path.join(self.data_path, collection_name)

            # 加载集合信息
            info_path = os.path.join(collection_dir, "info.json")
            if not os.path.exists(info_path):
                return

            with open(info_path, "r", encoding="utf-8") as f:
                collection_info = json.load(f)

            # 加载 FAISS 索引
            index_path = os.path.join(collection_dir, "index.faiss")
            if os.path.exists(index_path):
                index = faiss.read_index(index_path)
            else:
                # 如果索引文件不存在，创建空索引
                vector_dim = collection_info.get("vector_dim", 1024)
                index = self._create_faiss_index(vector_dim)

            # 加载元数据
            metadata_path = os.path.join(collection_dir, "metadata.pkl")
            if os.path.exists(metadata_path):
                with open(metadata_path, "rb") as f:
                    metadata = pickle.load(f)
            else:
                metadata = []

            # 存储到内存
            self.collections[collection_name] = collection_info
            self.indexes[collection_name] = index
            self.metadata[collection_name] = metadata

            self.logger.info(
                f"Loaded collection '{collection_name}' with {len(metadata)} records"
            )

        except Exception as e:
            self.logger.error(
                f"Failed to load collection '{collection_name}': {e}", exc_info=True
            )

    def _save_collections_metadata(self):
        """保存集合元数据"""
        try:
            metadata_file = os.path.join(self.data_path, "collections.json")
            collections_metadata = {
                name: {
                    "vector_dim": info["vector_dim"],
                    "created_time": info["created_time"],
                    "record_count": info["record_count"],
                }
                for name, info in self.collections.items()
            }

            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(collections_metadata, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.logger.error(
                f"Failed to save collections metadata: {e}", exc_info=True
            )

    def _load_collections_metadata(self):
        """加载集合元数据"""
        try:
            metadata_file = os.path.join(self.data_path, "collections.json")
            if os.path.exists(metadata_file):
                with open(metadata_file, "r", encoding="utf-8") as f:
                    collections_metadata = json.load(f)
                self.logger.debug(
                    f"Loaded metadata for {len(collections_metadata)} collections"
                )

        except Exception as e:
            self.logger.error(
                f"Failed to load collections metadata: {e}", exc_info=True
            )
