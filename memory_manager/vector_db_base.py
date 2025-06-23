from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum


class VectorDatabaseType(Enum):
    """向量数据库类型枚举"""

    MILVUS = "milvus"
    FAISS = "faiss"


class VectorDatabase(ABC):
    """
    向量数据库基类 - 支持多种向量数据库后端
    """

    def __init__(self, db_type: VectorDatabaseType):
        self.db_type = db_type
        self._is_connected = False

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """
        连接到数据库
        :return: 连接是否成功
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        断开数据库连接
        :return: 断开是否成功
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        检查连接状态
        :return: 是否已连接
        """
        pass

    @abstractmethod
    def create_collection(
        self, collection_name: str, schema: Dict[str, Any], **kwargs
    ) -> bool:
        """
        创建集合（表）
        :param collection_name: 集合名称
        :param schema: 集合的字段定义
        :param kwargs: 额外参数
        :return: 创建是否成功
        """
        pass

    @abstractmethod
    def has_collection(self, collection_name: str) -> bool:
        """
        检查集合是否存在
        :param collection_name: 集合名称
        :return: 集合是否存在
        """
        pass

    @abstractmethod
    def drop_collection(self, collection_name: str) -> bool:
        """
        删除指定的集合（包括其下的所有数据）
        :param collection_name: 要删除的集合名称
        :return: 删除是否成功
        """
        pass

    @abstractmethod
    def list_collections(self) -> List[str]:
        """
        获取所有集合名称
        :return: 集合名称列表
        """
        pass

    @abstractmethod
    def insert(
        self, collection_name: str, data: List[Dict[str, Any]], **kwargs
    ) -> bool:
        """
        插入数据
        :param collection_name: 集合名称
        :param data: 数据列表，每个元素是一个字典
        :param kwargs: 额外参数
        :return: 插入是否成功
        """
        pass

    @abstractmethod
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
        执行相似性搜索
        :param collection_name: 集合名称
        :param query_vectors: 查询向量列表
        :param top_k: 返回的最相似结果数量
        :param filters: 可选的过滤条件
        :param output_fields: 返回的字段列表
        :param kwargs: 额外参数
        :return: 搜索结果列表，每个查询向量对应一个结果列表
        """
        pass

    @abstractmethod
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
        :param collection_name: 集合名称
        :param filters: 查询条件表达式
        :param output_fields: 返回的字段列表
        :param limit: 限制返回数量
        :param kwargs: 额外参数
        :return: 查询结果
        """
        pass

    @abstractmethod
    def delete(self, collection_name: str, filters: str, **kwargs) -> bool:
        """
        根据条件删除记忆
        :param collection_name: 集合名称
        :param filters: 删除条件表达式
        :param kwargs: 额外参数
        :return: 删除是否成功
        """
        pass

    @abstractmethod
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        获取集合统计信息
        :param collection_name: 集合名称
        :return: 统计信息字典
        """
        pass

    def get_database_type(self) -> VectorDatabaseType:
        """
        获取数据库类型
        :return: 数据库类型
        """
        return self.db_type
