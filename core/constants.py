# -*- coding: utf-8 -*-
"""
Mnemosyne 插件常量定义
"""

# --- Milvus 相关常量 ---
DEFAULT_COLLECTION_NAME = "mnemosyne_default" # 修改了默认名称以更具辨识度
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_MILVUS_TIMEOUT = 5  # Milvus 查询超时时间（秒）
VECTOR_FIELD_NAME = "embedding"
PRIMARY_FIELD_NAME = "memory_id"
DEFAULT_OUTPUT_FIELDS = ["content", "create_time", PRIMARY_FIELD_NAME] # 默认查询返回字段

# --- 对话上下文相关常量 ---
DEFAULT_MAX_TURNS = 10       # 短期记忆最大对话轮数（用于总结）
DEFAULT_MAX_HISTORY = 20     # 短期记忆最大历史消息数（用于总结）

# --- RAG 相关常量 ---
DEFAULT_TOP_K = 5            # 默认检索的记忆数量
DEFAULT_PERSONA_ON_NONE = "UNKNOWN_PERSONA" # 当人格ID为空时使用的占位符或默认值