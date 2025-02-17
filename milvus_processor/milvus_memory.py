from pymilvus import (
    connections, Collection, FieldSchema,
    CollectionSchema, DataType, utility
)
from urllib.parse import urlparse
import numpy as np
import time
from pypinyin import lazy_pinyin
import re
import atexit

class MilvusMemory:
    # 类变量，标记是否已建立全局连接
    _connection_created = False

    def __init__(self, address='localhost:19530', embedding_dim=1024, collection_name='long_term_memory'):
        """
        :param address: Milvus 服务地址，支持格式如:
                        - "http://localhost:19530"
                        - "https://localhost:19530"
                        - "localhost:19530"
        :param embedding_dim: 向量维度
        :param collection_name: 集合名称
        """
        self.collection_name = self._fix_collection_name(collection_name)
        self.embedding_dim = embedding_dim
        self.host, self.port = self._parse_address(address)
        # 如果全局连接还未创建，则建立连接
        if not MilvusMemory._connection_created:
            connections.connect(alias="default", host=self.host, port=self.port)
            MilvusMemory._connection_created = True
            # 仅在第一次创建连接时注册退出时断开连接
            atexit.register(MilvusMemory.disconnect)

        self.collection = self._init_collection()

    @staticmethod
    def disconnect():
        """断开默认连接"""
        if connections.has_connection("default"):
            connections.disconnect("default")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # 在退出上下文时主动断开连接
        self.disconnect()

    def _fix_collection_name(self, name: str) -> str:
        """
        修正集合名称：
          - 如果传入的是中文，则全部转化为拼音；
          - 转换为小写；
          - 只保留字母、数字和下划线；
          - 如果首字符不是字母，则在前面加上前缀 'c'。
        """
        # 如果存在中文字符，则转换为拼音
        if re.search(r'[\u4e00-\u9fff]', name):
            name = ''.join(lazy_pinyin(name))
        new_name = name.lower()
        new_name = re.sub(r'[^a-z0-9_]', '', new_name)
        if not new_name or not new_name[0].isalpha():
            new_name = "c" + new_name
        return new_name

    def _parse_address(self, address: str):
        """
        解析地址，提取出主机名和端口号。
        如果地址没有协议前缀，则默认添加 "http://"
        """
        if not (address.startswith("http://") or address.startswith("https://")):
            address = "http://" + address
        parsed = urlparse(address)
        host = parsed.hostname
        port = parsed.port if parsed.port is not None else 19530  # 如果未指定端口，默认使用19530
        return host, port

    def _init_collection(self):
        """
        检查集合是否存在，不存在则创建集合，集合包含：
          - 自增主键 id
          - 向量字段 embedding（维度由 embedding_dim 参数决定）
          - 元数据字段 metadata（如对话内容、时间戳等）
        同时创建索引以加速向量检索。
        """
        if not utility.has_collection(self.collection_name):
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
                FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=1000),
                FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=30)
            ]
            schema = CollectionSchema(fields, description="长期记忆存储")
            collection = Collection(name=self.collection_name, schema=schema)

            # 创建索引，这部分参数还未进行调整
            index_params = {
                "index_type": "IVF_FLAT",
                "metric_type": "L2",
                "params": {"nlist": 256}
            }
            collection.create_index(field_name="embedding", index_params=index_params)
            # print(f"集合 {self.collection_name} 创建成功，并创建了索引。")
        else:
            collection = Collection(self.collection_name)
            # print(f"集合 {self.collection_name} 已存在。")
        return collection

    def add_memory(self, embedding, metadata):
        """
        添加一条长期记忆记录
        :param embedding: 向量数据，长度需与 embedding_dim 一致
        :param metadata: 附加的元数据（例如对话文本、时间戳等）
        :return: 插入记录的状态信息
        """
        # 自动添加当前时间戳
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")  
        data = [
            [embedding],  # embedding 字段数据
            [metadata],    # metadata 字段数据
            [timestamp]
        ]
        res = self.collection.insert(data)
        self.collection.flush()  # 确保数据落盘
        return res

    def search_memory(self, query_embedding, top_k=5, threshold = None):
        """
        根据输入向量进行相似度搜索，返回最相似的记忆记录
        :param query_embedding: 查询向量
        :param top_k: 返回最相似记录的数量
        :return: 搜索结果列表
        """
        # 确保集合已加载到内存中
        self.collection.load()
        search_params = {
            "metric_type": "L2",
            "params": {"nprobe": 20}
        }
        results = self.collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["metadata","timestamp"]
        )

        # 如果设置了阈值，则过滤掉距离过大的结果
        if threshold is not None:
            filtered_results = []
            for hit_list in results:
                filtered_hit_list = [hit for hit in hit_list if hit.distance <= threshold]
                filtered_results.append(filtered_hit_list)
            results = filtered_results
        return results

    def delete_all_collections(self):
        """删除Milvus中所有集合"""
        for collection_name in utility.list_collections():
            utility.drop_collection(collection_name)

    def list_collections(self):
        """返回当前所有集合名称"""
        return utility.list_collections()

    def delete_collection(self, collection_name):
        """删除指定集合（自动处理集合名称格式）"""
        fixed_name = self._fix_collection_name(collection_name)
        utility.drop_collection(fixed_name)