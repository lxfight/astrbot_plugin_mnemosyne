"""
Mnemosyne 插件初始化逻辑
包含配置加载、Schema 定义、Milvus 连接和设置、其他组件初始化等。
"""

import platform
from typing import TYPE_CHECKING

from pymilvus import CollectionSchema, DataType, FieldSchema

from astrbot.api.star import StarTools
from astrbot.core.log import LogManager

from ..memory_manager.context_manager import ConversationContextManager
from ..memory_manager.message_counter import MessageCounter
from ..memory_manager.vector_db.milvus_adapter import MilvusVectorDB
from ..memory_manager.vector_db.milvus_manager import MilvusManager

# 导入必要的类型和模块
from .constants import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_OUTPUT_FIELDS,
    PRIMARY_FIELD_NAME,
    VECTOR_FIELD_NAME,
)
from .tools import parse_address

# 类型提示，避免循环导入
if TYPE_CHECKING:
    from ..main import Mnemosyne

# 获取初始化专用的日志记录器
init_logger = LogManager.GetLogger(log_name="MnemosyneInit")


def initialize_config_check(plugin: "Mnemosyne"):
    """
    一些必要的参数检查可以放在这里

    B0 修复: 修正配置验证逻辑
    """
    astrbot_config = plugin.context.get_config()
    # ------ 检查num_pairs ------
    num_pairs = plugin.config["num_pairs"]
    # num_pairs需要小于['provider_settings']['max_context_length']配置的数量，如果该配置为-1，则不限制。
    astrbot_max_context_length = astrbot_config["provider_settings"][
        "max_context_length"
    ]
    # B0 修复: 修正验证逻辑，num_pairs 应该直接与 astrbot_max_context_length 比较
    # 因为 num_pairs 表示的是对话轮数，每轮包含用户和助手两条消息
    if astrbot_max_context_length > 0 and num_pairs > astrbot_max_context_length:
        # 安全处理：不在异常消息中暴露具体配置值
        error_detail = f"num_pairs({num_pairs})不能大于astrbot的配置(最多携带对话数量):{astrbot_max_context_length}"
        init_logger.error(error_detail)
        raise ValueError(
            "配置错误：num_pairs 的值超过了 AstrBot 的最大上下文长度限制。请检查配置文件并调整 num_pairs 的值。"
        )
    elif astrbot_max_context_length == 0:
        # 安全处理：不在异常消息中暴露具体配置值
        error_detail = (
            f"astrbot 的最大上下文长度配置值为 {astrbot_max_context_length}，必须大于0"
        )
        init_logger.error(error_detail)
        raise ValueError(
            "配置错误：AstrBot 的最大上下文长度必须大于0。请检查 AstrBot 配置文件中的 max_context_length 设置。"
        )
    # ------ num_pairs ------

    # ------ 检查contexts_memory_len ------
    contexts_memory_len = plugin.config.get("contexts_memory_len", 0)
    if (
        astrbot_max_context_length > 0
        and contexts_memory_len > astrbot_max_context_length
    ):
        # 安全处理：不在异常消息中暴露具体配置值
        error_detail = f"contexts_memory_len({contexts_memory_len})不能大于astrbot的配置:{astrbot_max_context_length}"
        init_logger.error(error_detail)
        raise ValueError(
            "配置错误：contexts_memory_len 的值超过了 AstrBot 的最大上下文长度限制。请检查配置文件。"
        )
    # ------ contexts_memory_len ------


def initialize_config_and_schema(plugin: "Mnemosyne"):
    """解析配置、验证和定义模式/索引参数。"""
    init_logger.debug("开始初始化配置和 Schema...")
    try:
        embedding_dim = plugin.config.get("embedding_dim", DEFAULT_EMBEDDING_DIM)
        if not isinstance(embedding_dim, int) or embedding_dim <= 0:
            raise ValueError("配置 'embedding_dim' 必须是一个正整数。")

        fields = [
            FieldSchema(
                name=PRIMARY_FIELD_NAME,
                dtype=DataType.INT64,
                is_primary=True,
                auto_id=True,
                description="唯一记忆标识符",
            ),
            FieldSchema(
                name="personality_id",
                dtype=DataType.VARCHAR,
                max_length=256,
                description="与记忆关联的角色ID",
            ),
            FieldSchema(
                name="session_id",
                dtype=DataType.VARCHAR,
                max_length=72,
                description="会话ID",
            ),  # 增加了长度限制
            FieldSchema(
                name="content",
                dtype=DataType.VARCHAR,
                max_length=4096,
                description="记忆内容（摘要或片段）",
            ),  # 增加了长度限制
            FieldSchema(
                name=VECTOR_FIELD_NAME,
                dtype=DataType.FLOAT_VECTOR,
                dim=embedding_dim,
                description="记忆的嵌入向量",
            ),
            FieldSchema(
                name="create_time",
                dtype=DataType.INT64,
                description="创建记忆时的时间戳（Unix epoch）",
            ),
        ]

        plugin.collection_name = plugin.config.get(
            "collection_name", DEFAULT_COLLECTION_NAME
        )
        plugin.collection_schema = CollectionSchema(
            fields=fields,
            description=f"长期记忆存储: {plugin.collection_name}",
            primary_field=PRIMARY_FIELD_NAME,
            enable_dynamic_field=plugin.config.get(
                "enable_dynamic_field", False
            ),  # 是否允许动态字段
        )

        # 定义索引参数
        plugin.index_params = plugin.config.get(
            "index_params",
            {
                "metric_type": "L2",  # 默认度量类型
                "index_type": "AUTOINDEX",  # 默认索引类型
                "params": {},
            },
        )
        # 定义搜索参数
        plugin.search_params = plugin.config.get(
            "search_params",
            {
                "metric_type": plugin.index_params.get(
                    "metric_type", "L2"
                ),  # 必须匹配索引度量类型
                "params": {"nprobe": 10},  # IVF_* 的示例搜索参数, AutoIndex 通常不需要
            },
        )

        plugin.output_fields_for_query = plugin.config.get(
            "output_fields", DEFAULT_OUTPUT_FIELDS
        )
        # 确保主键总是在输出字段中 (Milvus 可能默认包含，但明确指定更安全)
        # if PRIMARY_FIELD_NAME not in plugin.output_fields_for_query:
        #     plugin.output_fields_for_query.append(PRIMARY_FIELD_NAME)

        init_logger.debug(f"集合 Schema 定义完成: '{plugin.collection_name}'")
        init_logger.debug(f"索引参数: {plugin.index_params}")
        init_logger.debug(f"搜索参数: {plugin.search_params}")
        init_logger.debug(f"查询输出字段: {plugin.output_fields_for_query}")
        init_logger.debug("配置和 Schema 初始化成功。")

    except Exception as e:
        init_logger.error(f"初始化配置和 Schema 失败: {e}", exc_info=True)
        raise  # 重新抛出异常，以便在主 __init__ 中捕获


def initialize_milvus(plugin: "Mnemosyne"):
    """
    初始化 MilvusManager。
    根据配置决定连接到 Milvus Lite 或标准 Milvus 服务器，
    并进行必要的集合与索引设置。

    注意：Windows 系统不支持 Milvus Lite，自动使用标准 Milvus。
    """
    init_logger.debug("开始初始化 Milvus 连接和设置...")
    connect_args = {}  # 用于收集传递给 MilvusManager 的参数
    is_lite_mode = False  # 标记是否为 Lite 模式

    # 检测操作系统：Windows 不支持 Milvus Lite
    is_windows = platform.system() == "Windows"
    if is_windows:
        init_logger.info(
            "检测到 Windows 系统，Milvus Lite 不支持 Windows，将使用标准 Milvus"
        )

    try:
        # 1. 优先检查 Milvus Lite 配置（仅在非 Windows 系统上）
        lite_path = plugin.config.get("milvus_lite_path", "") if not is_windows else ""

        # 2. 获取标准 Milvus 的地址配置
        milvus_address = plugin.config.get("address")

        if lite_path and not is_windows:
            # --- 检测到 Milvus Lite 配置（非 Windows）---
            init_logger.info(f"检测到 Milvus Lite 配置，将使用本地路径: '{lite_path}'")
            connect_args["lite_path"] = lite_path
            is_lite_mode = True
            if milvus_address:
                init_logger.warning(
                    f"同时配置了 'milvus_lite_path' 和 'address'，将优先使用 Lite 路径，忽略 'address' ('{milvus_address}')。"
                )

        elif milvus_address:
            # --- 未配置 Lite 路径或为 Windows 系统，使用标准 Milvus 地址 ---
            init_logger.info(
                f"将根据 'address' 配置连接标准 Milvus: '{milvus_address}'"
            )
            is_lite_mode = False
            # 判断 address 是 URI 还是 host:port
            if milvus_address.startswith(("http://", "https://", "unix:")):
                init_logger.debug(f"地址 '{milvus_address}' 被识别为 URI。")
                connect_args["uri"] = milvus_address
            else:
                init_logger.debug(f"地址 '{milvus_address}' 将被解析为 host:port。")
                try:
                    host, port = parse_address(milvus_address)  # 使用工具函数解析
                    connect_args["host"] = host
                    connect_args["port"] = port
                except ValueError as e:
                    raise ValueError(
                        f"解析标准 Milvus 地址 '{milvus_address}' (host:port 格式) 失败: {e}"
                    ) from e
        else:
            # --- 既没有 Lite 路径也没有标准地址 ---
            init_logger.warning(
                "未配置 Milvus Lite 路径和标准 Milvus 地址。将使用标准插件数据目录"
            )

        # 3. 添加通用参数 (对 Lite 和 Standard 都可能有效)
        #    添加数据库名称 (db_name)
        db_name = plugin.config.get("db_name", "default")  # 提供默认值 'default'
        # 只有当 db_name 不是 'default' 时才显式添加到参数中，以保持简洁
        if db_name != "default":
            connect_args["db_name"] = db_name
            init_logger.info(f"将尝试连接到数据库: '{db_name}'。")
        else:
            init_logger.debug("将使用默认数据库 'default'。")

        #    设置连接别名
        #    如果未配置，生成一个基于集合名的默认别名
        alias = plugin.config.get(
            "connection_alias", f"mnemosyne_{plugin.collection_name}"
        )
        connect_args["alias"] = alias
        init_logger.debug(f"设置 Milvus 连接别名为: '{alias}'。")

        # 4. 添加仅适用于标准 Milvus 的参数 (如果不是 Lite 模式)
        if not is_lite_mode:
            init_logger.debug("为标准 Milvus 连接添加认证和安全设置（如果已配置）。")
            # 安全地获取认证配置字典，如果不存在则为空字典
            auth_config = plugin.config.get("authentication", {})

            # 添加可选的认证和安全参数
            added_auth_params = []
            for key in ["user", "password", "token", "secure"]:
                if key in auth_config and auth_config[key] is not None:
                    # 特别处理 'secure'，确保它是布尔值
                    if key == "secure":
                        value = auth_config[key]
                        if isinstance(value, str):
                            # 从字符串 'true'/'false' (不区分大小写) 转为布尔值
                            secure_bool = value.lower() == "true"
                        else:
                            # 尝试直接转为布尔值
                            secure_bool = bool(value)
                        connect_args[key] = secure_bool
                        added_auth_params.append(f"{key}={secure_bool}")
                    else:
                        connect_args[key] = auth_config[key]
                        # 安全处理：永远不记录 password 和 token 的真实值
                        if key not in ["password", "token"]:
                            added_auth_params.append(f"{key}={auth_config[key]}")
                        else:
                            # 使用脱敏处理，只显示配置项存在
                            added_auth_params.append(f"{key}=***")  # 隐藏敏感值

            if added_auth_params:
                init_logger.info(
                    f"从配置中添加了标准连接参数: {', '.join(added_auth_params)}"
                )
            else:
                init_logger.debug("未找到额外的认证或安全配置。")

        else:  # is_lite_mode is True
            # 检查并警告：如果在 Lite 模式下配置了不适用的参数
            auth_config = plugin.config.get("authentication", {})
            ignored_keys = [
                k
                for k in ["user", "password", "token", "secure"]
                if k in auth_config and auth_config[k] is not None
            ]
            if ignored_keys:
                init_logger.warning(
                    f"当前为 Milvus Lite 模式，配置中的以下认证/安全参数将被忽略: {ignored_keys}"
                )

        # 5. 选择使用 MilvusManager 或 MilvusVectorDB
        use_adapter = plugin.config.get("use_milvus_adapter", False)

        # 安全处理：创建用于日志记录的参数副本，敏感信息脱敏
        loggable_connect_args = {}
        for k, v in connect_args.items():
            if k in ["password", "token"]:
                loggable_connect_args[k] = "***"  # 完全隐藏敏感值
            else:
                loggable_connect_args[k] = v

        if use_adapter:
            # 使用新的 MilvusVectorDB 适配器
            init_logger.info(
                f"准备使用以下参数初始化 MilvusVectorDB 适配器: {loggable_connect_args}"
            )
            plugin.milvus_adapter = MilvusVectorDB(**connect_args)

            # 不再在初始化时检查连接，而是延迟到首次使用时
            if not plugin.milvus_adapter:
                raise RuntimeError("创建 MilvusVectorDB 适配器实例失败。请检查配置。")

            mode_name = (
                "Milvus Lite"
                if plugin.milvus_adapter._manager._is_lite
                else "标准 Milvus"
            )
            init_logger.info(
                f"MilvusVectorDB 适配器已初始化，连接将在首次使用时建立 ({mode_name}, 别名: {alias})。"
            )

            # 为了向后兼容，将适配器的 manager 赋值给 milvus_manager
            plugin.milvus_manager = plugin.milvus_adapter._manager
        else:
            # 使用原始的 MilvusManager（默认，保持向后兼容）
            init_logger.info(
                f"准备使用以下参数初始化 MilvusManager: {loggable_connect_args}"
            )

            # 创建 MilvusManager 实例
            # 注意：不在初始化时立即连接，而是延迟到首次使用时连接
            # 这样可以容错处理配置检查和初始化步骤
            plugin.milvus_manager = MilvusManager(**connect_args)

            # 6. 不再在初始化时检查连接，而是记录已准备好
            if not plugin.milvus_manager:
                mode_name = "Milvus Lite" if is_lite_mode else "标准 Milvus"
                raise RuntimeError("创建 MilvusManager 实例失败。请检查配置。")

            mode_name = (
                "Milvus Lite" if plugin.milvus_manager._is_lite else "标准 Milvus"
            )
            init_logger.info(
                f"MilvusManager 已初始化，连接将在首次使用时建立 ({mode_name}, 别名: {alias})。"
            )

        # 7. 设置集合和索引
        init_logger.debug("开始设置 Milvus 集合和索引...")
        setup_milvus_collection_and_index(plugin)
        init_logger.info("Milvus 集合和索引设置流程已调用。")

        init_logger.debug("Milvus 初始化流程成功完成。")

    except Exception as e:
        init_logger.error(
            f"Milvus 初始化或设置过程中发生错误: {e}", exc_info=True
        )  # exc_info=True 会记录堆栈跟踪
        plugin.milvus_manager = None  # 确保在初始化失败时 manager 被设为 None
        # 不再抛出异常，允许插件以降级模式运行


def setup_milvus_collection_and_index(plugin: "Mnemosyne"):
    """确保 Milvus 集合和索引存在并已加载。"""
    # 检查是否使用适配器
    use_adapter = plugin.config.get("use_milvus_adapter", False)

    # 获取管理器实例
    manager = None
    if use_adapter and hasattr(plugin, "milvus_adapter"):
        manager = plugin.milvus_adapter
    elif hasattr(plugin, "milvus_manager"):
        manager = plugin.milvus_manager

    if not manager or not plugin.collection_schema:
        init_logger.error("无法设置 Milvus 集合/索引：管理器或 Schema 未初始化。")
        raise RuntimeError(
            "MilvusManager/MilvusVectorDB 或 CollectionSchema 未准备好。"
        )

    collection_name = plugin.collection_name

    # 检查集合是否存在
    if manager.has_collection(collection_name):
        init_logger.info(f"集合 '{collection_name}' 已存在。开始检查 Schema 一致性...")
        check_schema_consistency(plugin, collection_name, plugin.collection_schema)
        # 注意: check_schema_consistency 目前只记录警告，不阻止后续操作
    else:
        # 如果集合不存在，则创建集合
        init_logger.info(f"未找到集合 '{collection_name}'。正在创建...")

        # 根据使用的类型选择创建方法
        if use_adapter:
            # 使用适配器创建集合（传递 CollectionSchema 对象）
            # 注意：MilvusVectorDB 的 create_collection 方法接受 dict，但这里需要处理类型
            from ..memory_manager.vector_db.schema_utils import (
                collection_schema_to_dict,
            )

            schema_dict = collection_schema_to_dict(plugin.collection_schema)
            # 类型注解：schema_dict 是 dict，但 create_collection 期望 CollectionSchema
            # 实际上适配器内部会处理这个转换
            manager.create_collection(collection_name, schema_dict)  # type: ignore
        else:
            # 使用管理器创建集合
            if not manager.create_collection(collection_name, plugin.collection_schema):
                raise RuntimeError(f"创建 Milvus 集合 '{collection_name}' 失败。")

        init_logger.info(f"成功创建集合 '{collection_name}'。")

    # 确保索引存在（只调用一次）
    ensure_milvus_index(plugin, collection_name)

    # 确保集合已加载到内存中以供搜索
    init_logger.info(f"确保集合 '{collection_name}' 已加载到内存...")
    max_retries = 3
    retry_count = 0
    load_success = False

    while retry_count < max_retries and not load_success:
        try:
            # 先检查集合是否已经加载
            from pymilvus import utility

            progress = utility.loading_progress(
                collection_name,
                using=manager.alias if hasattr(manager, "alias") else "default",
            )
            if progress and progress.get("loading_progress") == 100:
                init_logger.info(f"集合 '{collection_name}' 已处于加载状态。")
                load_success = True
                break

            # 尝试加载集合
            if manager.load_collection(collection_name, timeout=30):
                init_logger.info(f"集合 '{collection_name}' 已成功加载。")
                load_success = True
            else:
                retry_count += 1
                if retry_count < max_retries:
                    init_logger.warning(
                        f"加载集合 '{collection_name}' 失败，第 {retry_count} 次重试..."
                    )
                    import time

                    time.sleep(2)
                else:
                    init_logger.error(
                        f"加载集合 '{collection_name}' 失败（已重试 {max_retries} 次）。搜索功能可能无法正常工作。"
                    )
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                init_logger.warning(
                    f"加载集合 '{collection_name}' 时出错: {e}，第 {retry_count} 次重试..."
                )
                import time

                time.sleep(2)
            else:
                init_logger.error(
                    f"加载集合 '{collection_name}' 时出错（已重试 {max_retries} 次）: {e}。将在首次使用时重试加载。"
                )


def ensure_milvus_index(plugin: "Mnemosyne", collection_name: str):
    """检查向量字段的索引是否存在，如果不存在则创建它。"""
    # 检查是否使用适配器
    use_adapter = plugin.config.get("use_milvus_adapter", False)

    # 获取管理器实例
    manager = None
    if use_adapter and hasattr(plugin, "milvus_adapter"):
        manager = plugin.milvus_adapter._manager  # 适配器内部的管理器
    elif hasattr(plugin, "milvus_manager"):
        manager = plugin.milvus_manager

    if not manager:
        return

    try:
        has_vector_index = False
        # 先检查集合是否存在，避免后续操作出错
        if not manager.has_collection(collection_name):
            init_logger.warning(
                f"尝试为不存在的集合 '{collection_name}' 检查/创建索引，跳过。"
            )
            return

        # 检查向量字段是否有索引
        collection = manager.get_collection(collection_name)
        if collection:
            for index in collection.indexes:
                # 检查索引是否是为我们配置的向量字段创建的
                if index.field_name == VECTOR_FIELD_NAME:
                    # 可选：更严格地检查索引类型和参数是否匹配配置
                    # index_info = index.to_dict() if hasattr(index, 'to_dict') else {}
                    # configured_index_type = plugin.index_params.get('index_type')
                    # actual_index_type = index_info.get('index_type', index_info.get('index_param', {}).get('index_type')) # 兼容不同版本/API
                    # if configured_index_type and actual_index_type and configured_index_type != actual_index_type:
                    #     init_logger.warning(f"集合 '{collection_name}' 字段 '{VECTOR_FIELD_NAME}' 的索引类型 ({actual_index_type}) 与配置 ({configured_index_type}) 不符。")
                    # else:
                    init_logger.info(
                        f"在集合 '{collection_name}' 上检测到字段 '{VECTOR_FIELD_NAME}' 的现有索引。"
                    )
                    has_vector_index = True
                    break  # 找到即可退出循环
        else:
            init_logger.warning(
                f"无法获取集合 '{collection_name}' 的对象来详细验证索引信息。"
            )

        # 如果没有找到向量索引，则尝试创建
        if not has_vector_index:
            init_logger.warning(
                f"集合 '{collection_name}' 的向量字段 '{VECTOR_FIELD_NAME}' 尚未创建索引。正在尝试创建..."
            )
            # 使用配置好的索引参数创建索引
            index_success = manager.create_index(
                collection_name=collection_name,
                field_name=VECTOR_FIELD_NAME,
                index_params=plugin.index_params,
                # index_name=f"{VECTOR_FIELD_NAME}_idx" # 可以指定索引名，可选
                timeout=plugin.config.get(
                    "create_index_timeout", 600
                ),  # 增加创建索引的超时设置
            )
            if not index_success:
                init_logger.error(
                    f"为字段 '{VECTOR_FIELD_NAME}' 创建索引失败。搜索性能将受到严重影响。请检查 Milvus 日志。"
                )
                # 根据需要，可以考虑抛出异常
            else:
                init_logger.info(
                    f"已为字段 '{VECTOR_FIELD_NAME}' 发送索引创建请求。索引将在后台构建。"
                )
                # 创建索引后，可能需要等待其构建完成才能获得最佳性能，但通常可以继续运行
                # 可以考虑添加一个检查索引状态的步骤，或者在首次搜索前强制 load

    except Exception as e:
        init_logger.error(f"检查或创建集合 '{collection_name}' 的索引时发生错误: {e}")
        # 决定是否重新抛出异常，这可能会阻止插件启动
        raise


def _migrate_data_if_needed(old_dir: str, new_dir: str):
    """
    如果插件数据曾存储在其他位置，自动将其迁移到新位置。

    Args:
        old_dir (str): 旧的数据目录路径
        new_dir (str): 新的数据目录路径
    """
    import shutil
    from pathlib import Path

    old_path = Path(old_dir)
    new_path = Path(new_dir)

    # 如果旧目录存在且新目录不同
    if old_path.exists() and old_path != new_path:
        try:
            # 检查旧目录中是否有数据
            old_files = list(old_path.glob("*"))
            if old_files:
                new_path.mkdir(parents=True, exist_ok=True)
                for file in old_files:
                    new_file = new_path / file.name
                    if file.is_file():
                        if not new_file.exists():
                            shutil.copy2(file, new_file)
                            init_logger.info(f"已迁移数据文件: {file.name}")
                    elif file.is_dir():
                        if not new_file.exists():
                            shutil.copytree(file, new_file)
                            init_logger.info(f"已迁移数据目录: {file.name}")
                init_logger.info(f"已完成从 '{old_dir}' 到 '{new_dir}' 的数据迁移")
        except Exception as e:
            init_logger.warning(f"数据迁移失败: {e}，继续使用新位置")


def initialize_components(plugin: "Mnemosyne", plugin_data_dir=None):
    """初始化非 Milvus 的其他组件，如上下文管理器和消息计数器。"""
    init_logger.debug("开始初始化其他核心组件...")
    # 1. 初始化消息计数器和上下文管理器
    try:
        plugin.context_manager = ConversationContextManager()

        # 使用传入的 plugin_data_dir，或回退到 StarTools.get_data_dir()
        try:
            if plugin_data_dir is None:
                plugin_data_dir = StarTools.get_data_dir()
                init_logger.debug(f"从 StarTools 获取插件数据目录: {plugin_data_dir}")
            else:
                init_logger.debug(f"使用传入的插件数据目录: {plugin_data_dir}")

            # 检查是否需要迁移旧数据
            # 旧的相对路径：./mnemosyne_data 或 mnemosyne_data
            from pathlib import Path

            old_relative_dir = Path("./mnemosyne_data")
            if old_relative_dir.exists() and Path(plugin_data_dir) != old_relative_dir:
                init_logger.info("检测到旧的数据目录，启动数据迁移...")
                _migrate_data_if_needed(str(old_relative_dir), str(plugin_data_dir))

            plugin.msg_counter = MessageCounter(plugin_data_dir=str(plugin_data_dir))
            init_logger.debug(
                f"使用插件数据目录初始化 MessageCounter: {plugin_data_dir}"
            )
        except RuntimeError as e:
            # 如果获取失败，使用 MessageCounter 的后备机制
            init_logger.warning(
                f"无法获取数据目录，将使用 MessageCounter 的后备方案: {e}"
            )
            plugin.msg_counter = MessageCounter()

        init_logger.info("消息计数器和上下文管理器初始化成功。")
    except Exception as e:
        init_logger.error(f"消息计数器初始化失败:{e}", exc_info=True)
        raise

    # 注: Embedding Provider 已在 main.py 中异步初始化
    # embedding_provider 的初始化是非阻塞的，不会阻止插件启动

    init_logger.debug("其他核心组件初始化完成。")


def check_schema_consistency(
    plugin: "Mnemosyne", collection_name: str, expected_schema: CollectionSchema
):
    """
    检查现有集合的 Schema 是否与预期一致 (简化版，主要检查字段名和类型)。
    记录警告信息，但不阻止插件运行。
    """
    # 检查是否使用适配器
    use_adapter = plugin.config.get("use_milvus_adapter", False)

    # 获取管理器实例
    manager = None
    if use_adapter and hasattr(plugin, "milvus_adapter"):
        manager = plugin.milvus_adapter._manager  # 适配器内部的管理器
    elif hasattr(plugin, "milvus_manager"):
        manager = plugin.milvus_manager

    if not manager or not manager.has_collection(collection_name):
        # init_logger.info(f"集合 '{collection_name}' 不存在，无需检查一致性。")
        return True  # 没有可供比较的现有集合

    try:
        collection = manager.get_collection(collection_name)
        if not collection:
            init_logger.error(f"无法获取集合 '{collection_name}' 以检查 Schema。")
            return False  # 视为不一致

        actual_schema = collection.schema
        expected_fields = {f.name: f for f in expected_schema.fields}
        actual_fields = {f.name: f for f in actual_schema.fields}

        consistent = True
        warnings = []

        # 检查期望的字段是否存在以及基本类型是否匹配
        for name, expected_field in expected_fields.items():
            if name not in actual_fields:
                warnings.append(f"模式警告：配置中期望的字段 '{name}' 在实际集合中缺失")
                consistent = False
                continue  # 跳过对此字段的后续检查

            actual_field = actual_fields[name]
            # 检查数据类型
            if actual_field.dtype != expected_field.dtype:
                # 特别处理向量类型，检查维度
                is_vector_expected = expected_field.dtype in [
                    DataType.FLOAT_VECTOR,
                    DataType.BINARY_VECTOR,
                ]
                is_vector_actual = actual_field.dtype in [
                    DataType.FLOAT_VECTOR,
                    DataType.BINARY_VECTOR,
                ]

                if is_vector_expected and is_vector_actual:
                    expected_dim = expected_field.params.get("dim")
                    actual_dim = actual_field.params.get("dim")
                    if expected_dim != actual_dim:
                        warnings.append(
                            f"模式警告：字段 '{name}' 的向量维度不匹配 (预期 {expected_dim}, 实际 {actual_dim})"
                        )
                        consistent = False
                elif (
                    expected_field.dtype == DataType.VARCHAR
                    and actual_field.dtype == DataType.VARCHAR
                ):
                    # 检查 VARCHAR 的 max_length
                    expected_len = expected_field.params.get("max_length")
                    actual_len = actual_field.params.get("max_length")
                    # 如果实际长度小于预期，可能导致数据截断，发出警告
                    # 如果实际长度大于预期，通常没问题，但也可能提示一下
                    if (
                        expected_len is not None
                        and actual_len is not None
                        and actual_len < expected_len
                    ):
                        warnings.append(
                            f"模式警告：字段 '{name}' 的 VARCHAR 长度不足 (预期 {expected_len}, 实际 {actual_len})"
                        )
                        consistent = False  # 这可能比较严重
                    elif (
                        expected_len is not None
                        and actual_len is not None
                        and actual_len > expected_len
                    ):
                        warnings.append(
                            f"模式提示：字段 '{name}' 的 VARCHAR 长度大于预期 (预期 {expected_len}, 实际 {actual_len})"
                        )
                        # consistent = False # 通常不认为是严重问题
                else:
                    # 其他类型不匹配
                    warnings.append(
                        f"模式警告：字段 '{name}' 的数据类型不匹配 (预期 {expected_field.dtype}, 实际 {actual_field.dtype})"
                    )
                    consistent = False

            # 检查主键属性
            if actual_field.is_primary != expected_field.is_primary:
                warnings.append(f"模式警告：字段 '{name}' 的主键状态不匹配")
                consistent = False
            # 检查 auto_id 属性 (仅当是主键时有意义)
            if (
                expected_field.is_primary
                and actual_field.auto_id != expected_field.auto_id
            ):
                warnings.append(f"模式警告：主键字段 '{name}' 的 AutoID 状态不匹配")
                consistent = False

        # 检查实际集合中是否存在配置中未定义的字段
        for name in actual_fields:
            if name not in expected_fields:
                # 如果允许动态字段，这可能是正常的
                enable_dynamic = getattr(
                    plugin.collection_schema, "enable_dynamic_field", False
                )
                if not enable_dynamic:
                    warnings.append(
                        f"模式警告：发现未在配置中定义的字段 '{name}' (且未启用动态字段)"
                    )
                    # consistent = False # 是否视为不一致取决于策略

        if not consistent:
            warning_message = (
                f"集合 '{collection_name}' 的 Schema 与当前配置存在潜在不一致:\n - "
                + "\n - ".join(warnings)
            )
            warning_message += "\n请检查您的 Milvus 集合结构或插件配置。不一致可能导致运行时错误或数据问题。"
            init_logger.warning(warning_message)
        else:
            init_logger.info(f"集合 '{collection_name}' 的 Schema 与当前配置基本一致。")

        return consistent

    except Exception as e:
        init_logger.error(
            f"检查集合 '{collection_name}' Schema 一致性时发生错误: {e}", exc_info=True
        )
        return False  # 将错误视为不一致
