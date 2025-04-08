# -*- coding: utf-8 -*-
"""
Mnemosyne 插件初始化逻辑
包含配置加载、Schema 定义、Milvus 连接和设置、其他组件初始化等。
"""

from typing import TYPE_CHECKING

from pymilvus import CollectionSchema, FieldSchema, DataType

from astrbot.core.log import LogManager

# 导入必要的类型和模块
from .constants import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_EMBEDDING_DIM,
    PRIMARY_FIELD_NAME,
    VECTOR_FIELD_NAME,
    DEFAULT_OUTPUT_FIELDS,
)
from .tools import parse_address

from ..memory_manager.message_counter import MessageCounter
from ..memory_manager.vector_db.milvus_manager import MilvusManager
from ..memory_manager.embedding import OpenAIEmbeddingAPI

# 类型提示，避免循环导入
if TYPE_CHECKING:
    from ..main import Mnemosyne

# 获取初始化专用的日志记录器
init_logger = LogManager.GetLogger(log_name="MnemosyneInit")


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
    """初始化 MilvusManager，连接并设置集合/索引。"""
    init_logger.debug("开始初始化 Milvus 连接和设置...")
    try:
        milvus_address = plugin.config.get("address")
        if not milvus_address:
            raise ValueError(
                "Milvus 'address' (例如 'localhost:19530' 或 URI) 未在配置中指定。"
            )

        # 根据地址格式确定连接参数
        if milvus_address.startswith(("http://", "https://", "unix:")):
            connect_args = {"uri": milvus_address}
        else:
            try:
                host, port = parse_address(milvus_address)  # 使用工具函数解析
                connect_args = {"host": host, "port": port}
            except ValueError as e:
                raise ValueError(
                    f"解析 Milvus 地址 '{milvus_address}' 失败: {e}"
                ) from e

        # 从配置中添加可选的连接参数
        for key in [
            "user",
            "password",
            "token",
            "secure",
            "db_name",
            "server_pem_path",
            "server_key_path",
            "ca_pem_path",
            "client_pem_path",
            "client_key_path",
        ]:
            if key in plugin.config:
                connect_args[key] = plugin.config[key]

        # 设置连接别名，虽然 MilvusManager 内部可能不直接使用，但保持配置选项
        connect_args["alias"] = plugin.config.get(
            "connection_alias", f"mnemosyne_{plugin.collection_name}"
        )  # 使用更有意义的别名

        init_logger.info(
            f"尝试使用参数连接到 Milvus: { {k: v for k, v in connect_args.items() if k != 'password' and k != 'token'} }"
        )  # 不打印敏感信息
        plugin.milvus_manager = MilvusManager(**connect_args)

        if not plugin.milvus_manager or not plugin.milvus_manager.is_connected():
            raise ConnectionError(
                "初始化 MilvusManager 或连接到 Milvus 失败。请检查配置和 Milvus 服务状态。"
            )

        init_logger.info(f"成功连接到 Milvus (Alias: {connect_args['alias']})。")

        # --- 集合和索引设置 ---
        setup_milvus_collection_and_index(plugin)
        init_logger.debug("Milvus 连接和设置完成。")

    except Exception as e:
        init_logger.error(f"Milvus 初始化或集合/索引设置失败: {e}", exc_info=True)
        plugin.milvus_manager = None  # 确保失败时 manager 为 None
        raise  # 重新抛出


def setup_milvus_collection_and_index(plugin: "Mnemosyne"):
    """确保 Milvus 集合和索引存在并已加载。"""
    if not plugin.milvus_manager or not plugin.collection_schema:
        init_logger.error("无法设置 Milvus 集合/索引：管理器或 Schema 未初始化。")
        raise RuntimeError("MilvusManager 或 CollectionSchema 未准备好。")

    collection_name = plugin.collection_name

    # 检查集合是否存在
    if plugin.milvus_manager.has_collection(collection_name):
        init_logger.info(f"集合 '{collection_name}' 已存在。开始检查 Schema 一致性...")
        check_schema_consistency(plugin, collection_name, plugin.collection_schema)
        # 注意: check_schema_consistency 目前只记录警告，不阻止后续操作
    else:
        # 如果集合不存在，则创建集合
        init_logger.info(f"未找到集合 '{collection_name}'。正在创建...")
        if not plugin.milvus_manager.create_collection(
            collection_name, plugin.collection_schema
        ):
            raise RuntimeError(f"创建 Milvus 集合 '{collection_name}' 失败。")
        init_logger.info(f"成功创建集合 '{collection_name}'。")
        # 创建集合后立即尝试创建索引
        ensure_milvus_index(plugin, collection_name)

    # 再次确保索引存在（即使集合已存在也检查一遍）
    ensure_milvus_index(plugin, collection_name)

    # 确保集合已加载到内存中以供搜索
    init_logger.info(f"确保集合 '{collection_name}' 已加载到内存...")
    if not plugin.milvus_manager.load_collection(collection_name):
        # 加载失败可能是资源问题或索引未就绪，打印错误但可能允许插件继续（取决于容错策略）
        init_logger.error(
            f"加载集合 '{collection_name}' 失败。搜索功能可能无法正常工作或效率低下。"
        )
        # 可以考虑在这里抛出异常，如果加载是强制要求的话
        # raise RuntimeError(f"加载 Milvus 集合 '{collection_name}' 失败。")
    else:
        init_logger.info(f"集合 '{collection_name}' 已成功加载。")


def ensure_milvus_index(plugin: "Mnemosyne", collection_name: str):
    """检查向量字段的索引是否存在，如果不存在则创建它。"""
    if not plugin.milvus_manager:
        return

    try:
        has_vector_index = False
        # 先检查集合是否存在，避免后续操作出错
        if not plugin.milvus_manager.has_collection(collection_name):
            init_logger.warning(
                f"尝试为不存在的集合 '{collection_name}' 检查/创建索引，跳过。"
            )
            return

        # 检查向量字段是否有索引
        collection = plugin.milvus_manager.get_collection(collection_name)
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
            index_success = plugin.milvus_manager.create_index(
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
        init_logger.error(
            f"检查或创建集合 '{collection_name}' 的索引时发生错误: {e}"
        )
        # 决定是否重新抛出异常，这可能会阻止插件启动
        raise


def initialize_components(plugin: "Mnemosyne"):
    """初始化非 Milvus 的其他组件，如上下文管理器和嵌入 API。"""
    init_logger.debug("开始初始化其他核心组件...")
    # 1. 初始化消息计数器
    try:
        plugin.msg_counter = MessageCounter()
        init_logger.info("消息计数器初始化成功。")
    except Exception as e:
        init_logger.error(f"消息计数器初始化失败:{e}")
        raise

    # 2. 初始化 Embedding API
    try:
        # 检查必要的配置是否存在
        required_keys = ["embedding_model", "embedding_key", "embedding_url"]
        missing_keys = [key for key in required_keys if not plugin.config.get(key)]
        if missing_keys:
            raise ValueError(f"缺少 Embedding API 的配置项: {', '.join(missing_keys)}")

        plugin.ebd = OpenAIEmbeddingAPI(
            model=plugin.config.get("embedding_model"),
            api_key=plugin.config.get("embedding_key"),
            base_url=plugin.config.get("embedding_url"),
        )
        # 尝试测试连接（如果API提供此功能）
        # 注意：这里假设 OpenAIEmbeddingAPI 有一个 test_connection 方法，如果没有需要调整
        try:
            plugin.ebd.test_connection()  # 假设此方法在失败时抛出异常
            init_logger.info("Embedding API 初始化成功，连接测试通过。")
        except AttributeError:
            init_logger.warning(
                "Embedding API 类没有 test_connection 方法，跳过连接测试。"
            )
        except Exception as conn_err:
            init_logger.error(f"Embedding API 连接测试失败: {conn_err}", exc_info=True)
            # 决定是否允许插件在 Embedding API 连接失败时继续运行
            # raise ConnectionError(f"无法连接到 Embedding API: {conn_err}") from conn_err
            init_logger.warning("将继续运行，但 Embedding 功能将不可用。")
            plugin.ebd = None  # 明确设为 None 表示不可用

    except Exception as e:
        init_logger.error(f"初始化 Embedding API 失败: {e}", exc_info=True)
        plugin.ebd = None  # 确保失败时 ebd 为 None
        raise  # Embedding 是核心功能，失败则插件无法工作

    init_logger.debug("其他核心组件初始化完成。")


def check_schema_consistency(
    plugin: "Mnemosyne", collection_name: str, expected_schema: CollectionSchema
):
    """
    检查现有集合的 Schema 是否与预期一致 (简化版，主要检查字段名和类型)。
    记录警告信息，但不阻止插件运行。
    """
    if not plugin.milvus_manager or not plugin.milvus_manager.has_collection(
        collection_name
    ):
        # init_logger.info(f"集合 '{collection_name}' 不存在，无需检查一致性。")
        return True  # 没有可供比较的现有集合

    try:
        collection = plugin.milvus_manager.get_collection(collection_name)
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
                if not plugin.collection_schema.enable_dynamic_field:
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
