"""
向量数据库模块

此模块提供了多种向量数据库实现和工具函数，包括：
- MilvusManager: 底层 Milvus 连接和管理
- MilvusVectorDB: 新的适配器实现（推荐使用）
- MilvusDatabase: 旧的实现（已废弃，仅保持向后兼容）
- Schema 工具函数: 用于 Schema 转换和验证

版本信息:
- v2.0.0: 引入 MilvusVectorDB 适配器，废弃 MilvusDatabase
- v1.x.x: 原始 MilvusDatabase 实现

迁移指南:
1. 新项目应使用 MilvusVectorDB 替代 MilvusDatabase
2. MilvusVectorDB 提供更好的错误处理、连接管理和性能优化
3. 使用 schema_utils 模块中的函数进行 Schema 转换和验证
"""

# 导入依赖
from .milvus_adapter import MilvusVectorDB
from .milvus_manager import MilvusManager
from .schema_utils import (
    collection_schema_to_dict,
    dict_to_collection_schema,
    merge_schema_dicts,
    validate_schema_dict,
)


# 定义一个虚拟的 MilvusDatabase 类以保持向后兼容性
class MilvusDatabase:
    """虚拟的 MilvusDatabase 类，用于向后兼容（原文件已删除）"""

    def __init__(self, *args, **kwargs):
        raise ImportError(
            "MilvusDatabase 类已被移除，请使用 MilvusVectorDB 适配器类。"
            "详见模块顶部的迁移指南。"
        )

    def __new__(cls, *args, **kwargs):
        raise ImportError(
            "MilvusDatabase 类已被移除，请使用 MilvusVectorDB 适配器类。"
            "详见模块顶部的迁移指南。"
        )


# 定义模块的公共接口
__all__ = [
    # 新的推荐实现
    "MilvusVectorDB",
    # Schema 工具函数
    "dict_to_collection_schema",
    "collection_schema_to_dict",
    "merge_schema_dicts",
    "validate_schema_dict",
    # 底层管理器
    "MilvusManager",
    # 旧实现（已废弃，使用虚拟实现保持向后兼容）
    "MilvusDatabase",
]

# 版本信息
__version__ = "2.0.0"

# 模块文档（完整版本）
__doc__ = """
向量数据库模块

此模块提供了多种向量数据库实现和工具函数，包括：
- MilvusManager: 底层 Milvus 连接和管理
- MilvusVectorDB: 新的适配器实现（推荐使用）
- MilvusDatabase: 旧的实现（已废弃，仅保持向后兼容）
- Schema 工具函数: 用于 Schema 转换和验证

版本信息:
- v2.0.0: 引入 MilvusVectorDB 适配器，废弃 MilvusDatabase
- v1.x.x: 原始 MilvusDatabase 实现

迁移指南:
1. 新项目应使用 MilvusVectorDB 替代 MilvusDatabase
2. MilvusVectorDB 提供更好的错误处理、连接管理和性能优化
3. 使用 schema_utils 模块中的函数进行 Schema 转换和验证

使用示例:

# 使用新的 MilvusVectorDB 适配器（推荐）
from memory_manager.vector_db import MilvusVectorDB, dict_to_collection_schema

# 创建适配器实例
with MilvusVectorDB(host='localhost', port=19530) as db:
    # 定义 Schema
    schema_dict = {
        'fields': [
            {'name': 'id', 'dtype': DataType.INT64, 'is_primary': True, 'auto_id': True},
            {'name': 'content', 'dtype': DataType.VARCHAR, 'max_length': 1000},
            {'name': 'embedding', 'dtype': DataType.FLOAT_VECTOR, 'dim': 768}
        ]
    }

    # 创建集合
    db.create_collection('my_collection', schema_dict)

    # 插入数据
    data = [{'content': 'Hello', 'embedding': [0.1] * 768}]
    db.insert('my_collection', data)

    # 搜索数据
    results = db.search('my_collection', [0.1] * 768, top_k=5)
    print(results)

# 使用 Schema 工具函数
from memory_manager.vector_db import dict_to_collection_schema, collection_schema_to_dict

# 转换 Schema
schema_obj = dict_to_collection_schema(schema_dict)
schema_dict = collection_schema_to_dict(schema_obj)

# 使用底层 MilvusManager（高级用户）
from memory_manager.vector_db import MilvusManager

manager = MilvusManager(host='localhost', port=19530)
if manager.is_connected():
    print("连接成功")
    print(manager.get_connection_info())

# 使用旧的 MilvusDatabase（不推荐，会产生导入错误）
from memory_manager.vector_db import MilvusDatabase  # 会产生导入错误

db = MilvusDatabase('localhost', 19530)  # 会产生导入错误
"""
