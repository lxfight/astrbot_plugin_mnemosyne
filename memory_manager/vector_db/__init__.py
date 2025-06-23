# -*- coding: utf-8 -*-
"""
向量数据库模块
支持多种向量数据库后端：Milvus 和 FAISS
"""

from ..vector_db_base import VectorDatabase, VectorDatabaseType
from .milvus_manager import MilvusManager
from .faiss_manager import FaissManager
from .database_factory import VectorDatabaseFactory

__all__ = [
    "VectorDatabase",
    "VectorDatabaseType",
    "MilvusManager",
    "FaissManager",
    "VectorDatabaseFactory",
]
