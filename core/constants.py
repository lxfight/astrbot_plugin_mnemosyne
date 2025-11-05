"""
Mnemosyne 插件常量定义
"""

# --- Milvus 相关常量 ---
DEFAULT_COLLECTION_NAME = "mnemosyne_default"  # 修改了默认名称以更具辨识度
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_MILVUS_TIMEOUT = 5  # Milvus 查询超时时间（秒）
VECTOR_FIELD_NAME = "embedding"
PRIMARY_FIELD_NAME = "memory_id"
DEFAULT_OUTPUT_FIELDS = [
    "content",
    "create_time",
    PRIMARY_FIELD_NAME,
]  # 默认查询返回字段
# 查询记忆条数的上限
MAX_TOTAL_FETCH_RECORDS = 10000

# --- 对话上下文相关常量 ---
DEFAULT_MAX_TURNS = 10  # 短期记忆最大对话轮数（用于总结）
DEFAULT_MAX_HISTORY = 20  # 短期记忆最大历史消息数（用于总结）

# --- RAG 相关常量 ---
DEFAULT_TOP_K = 5  # 默认检索的记忆数量
DEFAULT_PERSONA_ON_NONE = "UNKNOWN_PERSONA"  # 当人格ID为空时使用的占位符或默认值

# --- 计时器相关 ---
DEFAULT_SUMMARY_CHECK_INTERVAL_SECONDS = 60  # 默认总结检查间隔 秒
DEFAULT_SUMMARY_TIME_THRESHOLD_SECONDS = 3600  # 默认时间阈值
