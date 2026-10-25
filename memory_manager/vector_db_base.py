from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorInsertResult:
    """统一的向量数据库写入结果。"""

    insert_count: int = 0
    primary_keys: list[Any] = field(default_factory=list)


@dataclass
class VectorDeleteResult:
    """统一的向量数据库删除结果。"""

    delete_count: int | None = None


class VectorDatabase(ABC):
    """
    向量数据库基类
    """

    @abstractmethod
    def connect(self, **kwargs):
        """
        连接到数据库
        """
        pass

    def is_connected(self) -> bool:
        """返回当前连接状态。"""
        return bool(getattr(self, "_is_connected", False))

    @abstractmethod
    def create_collection(self, collection_name: str, schema: dict[str, Any]):
        """
        创建集合（表）
        :param collection_name: 集合名称
        :param schema: 集合的字段定义
        """
        pass

    @abstractmethod
    def insert(
        self, collection_name: str, data: list[dict[str, Any]]
    ) -> VectorInsertResult:
        """
        插入数据
        :param collection_name: 集合名称
        :param data: 数据列表，每个元素是一个字典
        """
        pass

    def update(
        self,
        collection_name: str,
        record_id: str,
        data: dict[str, Any],
    ) -> VectorInsertResult:
        """更新单条记录；不支持原生更新的后端应显式抛出。"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support in-place updates"
        )

    def get_by_id(
        self,
        collection_name: str,
        record_id: str,
        output_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """按数据库原生 ID 获取单条记录。"""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support direct ID lookup"
        )

    def count(self, collection_name: str, filters: str | None = None) -> int | None:
        """返回匹配记录数；后端不支持原生计数时返回 None。"""
        return None

    @abstractmethod
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
        :param collection_name: 集合名称
        :param filters: 查询条件表达式
        :param output_fields: 返回的字段列表
        :return: 查询结果
        """
        pass

    def query_page(
        self,
        collection_name: str,
        filters: str | None,
        output_fields: list[str] | None,
        limit: int,
        cursor: Any = None,
    ) -> tuple[list[dict[str, Any]], Any]:
        """查询一页记录并返回下一页游标；默认将游标解释为整数 offset。"""
        offset = int(cursor or 0)
        records = self.query(
            collection_name=collection_name,
            filters=filters,
            output_fields=output_fields,
            limit=limit,
            offset=offset,
        )
        next_cursor = offset + len(records) if len(records) == limit else None
        return records, next_cursor

    @abstractmethod
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
        :param collection_name: 集合名称
        :param query_vector: 查询向量
        :param top_k: 返回的最相似结果数量
        :param filters: 可选的过滤条件
        :return: 搜索结果
        """
        pass

    @abstractmethod
    def close(self):
        """
        关闭数据库连接
        """
        pass

    @abstractmethod
    def list_collections(self) -> list[str]:
        """
        获取所有集合名称
        """
        pass

    def has_collection(self, collection_name: str) -> bool:
        """判断集合是否存在。"""
        return collection_name in self.list_collections()

    @abstractmethod
    def get_loaded_collections(self) -> list[str]:
        """获取已加载到内存的集合"""
        pass

    @abstractmethod
    def get_latest_memory(
        self, collection_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """获取最新插入的记忆"""
        pass

    @abstractmethod
    def delete(self, collection_name: str, expr: str) -> VectorDeleteResult:
        """根据条件删除记忆"""
        pass

    def flush(self, collection_names: list[str] | None = None) -> bool:
        """将挂起写入刷新到底层存储；不需要显式刷新的后端可直接返回 True。"""
        return True

    @abstractmethod
    def drop_collection(self, collection_name: str) -> bool:
        """
        删除指定的集合（包括其下的所有数据）

        :param collection_name: 要删除的集合名称
        """
        pass
