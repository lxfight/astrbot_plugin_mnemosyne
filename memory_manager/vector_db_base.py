from abc import ABC, abstractmethod
from typing import Any


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

    @abstractmethod
    def create_collection(self, collection_name: str, schema: dict[str, Any]):
        """
        创建集合（表）
        :param collection_name: 集合名称
        :param schema: 集合的字段定义
        """
        pass

    @abstractmethod
    def insert(self, collection_name: str, data: list[dict[str, Any]]):
        """
        插入数据
        :param collection_name: 集合名称
        :param data: 数据列表，每个元素是一个字典
        """
        pass

    @abstractmethod
    def query(
        self, collection_name: str, filters: str, output_fields: list[str]
    ) -> list[dict[str, Any]]:
        """
        根据条件查询数据
        :param collection_name: 集合名称
        :param filters: 查询条件表达式
        :param output_fields: 返回的字段列表
        :return: 查询结果
        """
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        top_k: int,
        filters: str | None = None,
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

    @abstractmethod
    def get_loaded_collections(self) -> list[str]:
        """获取已加载到内存的集合"""
        pass

    @abstractmethod
    def get_latest_memory(self, collection_name: str) -> dict[str, Any]:
        """获取最新插入的记忆"""
        pass

    @abstractmethod
    def delete(self, collection_name: str, expr: str):
        """根据条件删除记忆"""
        pass

    @abstractmethod
    def drop_collection(self, collection_name: str) -> None:
        """
        删除指定的集合（包括其下的所有数据）

        :param collection_name: 要删除的集合名称
        """
        pass
