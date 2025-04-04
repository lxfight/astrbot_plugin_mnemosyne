from typing import List, Dict, Optional, Any, Union
from urllib.parse import urlparse
import time


from pymilvus import connections, utility, CollectionSchema, DataType, Collection
from pymilvus.exceptions import (
    MilvusException,
    CollectionNotExistException,
    IndexNotExistException,
)
# 配置日志记录
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

from astrbot.core.log import LogManager

logger = LogManager.GetLogger(log_name="Mnemosyne")


class MilvusManager:
    """
    一个用于管理与 Milvus 数据库交互的类。
    封装了连接、集合管理、数据操作、索引和搜索等常用功能。
    支持通过 URI 或 host/port 进行连接。
    """

    def __init__(
        self,
        alias: str = "default",
        uri: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[Union[str, int]] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        secure: Optional[bool] = None,  # 添加 secure 参数
        token: Optional[str] = None,  # Milvus 2.2.9+ 支持 API Key / Token
        db_name: str = "default",  # Milvus 2.2+ 支持多数据库
        **kwargs,
    ):
        """
        初始化 MilvusManager。
        优先使用 'uri' 进行连接。如果 'uri' 未提供，则使用 'host' 和 'port'。
        必须提供 'uri' 或 ('host' 和 'port') 之一。
        Args:
            alias (str): 此连接的别名。
            uri (Optional[str]): Milvus 连接 URI。例如：
                - "http://localhost:19530"
                - "https://user:password@milvus.example.com:19530"
                - "https://your-reverse-proxy.com/milvus-path" (代理地址)
                - "unix:/path/to/milvus.sock" (如果 pymilvus 支持)
                如果提供，将忽略 host 和 port 参数。
            host (Optional[str]): Milvus 服务器的主机名或 IP 地址。仅在 uri 未提供时使用。
                                    默认为 "localhost"（如果 uri 和 host 都未提供）。
            port (Optional[Union[str, int]]): Milvus 服务器的端口。仅在 uri 未提供时使用。
                                                默认为 19530（如果 uri 和 port 都未提供）。
            user (Optional[str]): 用于身份验证的用户名 (如果 Milvus 启用 RBAC)。
                                    如果包含在 uri 中，uri 中的值优先。
            password (Optional[str]): 用于身份验证的密码 (如果 Milvus 启用 RBAC)。
                                        如果包含在 uri 中，uri 中的值优先。
            secure (Optional[bool]): 是否使用 TLS/SSL 安全连接。
                                        如果 uri 以 "https" 开头，通常应设为 True。
                                        如果 uri 未提供，根据需要设置。
            token (Optional[str]): 用于身份验证的 API Key 或 Token (Milvus 2.2.9+)。
                                    优先于 user/password。
            db_name (str): 要连接的数据库名称 (Milvus 2.2+)。默认为 "default"。
            **kwargs: 传递给 connections.connect 的其他参数。
        """

        self.alias = alias
        self._uri = uri
        self._host = host if host is not None else "localhost"  # 提供默认值以防万一
        self._port = str(port) if port is not None else "19530"  # 提供默认值并转为 str
        self._user = user
        self._password = password
        self._secure = secure
        self._token = token
        self._db_name = db_name
        self.connect_kwargs = kwargs  # 存储额外的连接参数

        self._connection_info = {}  # 用于存储最终传递给 connect 的参数
        self._is_connected = False

        # -- 参数优先级和验证 --
        if self._uri:
            logger.info(f"将使用 URI '{self._uri}' 进行连接 (别名: {self.alias})。")
            self._connection_info["uri"] = self._uri
            # 尝试从 URI 解析 user/password，除非已显式提供 token 或 user/pass
            parsed_uri = urlparse(self._uri)
            if not self._token:  # Token 优先级最高
                uri_user = parsed_uri.username
                uri_password = parsed_uri.password
                if uri_user and self._user is None:
                    self._user = uri_user
                    logger.info(f"从 URI 中提取到用户名 (别名: {self.alias})。")
                if uri_password and self._password is None:
                    self._password = uri_password
                    logger.info(f"从 URI 中提取到密码 (别名: {self.alias})。")
            # 如果 secure 未显式设置，尝试从 URI scheme 推断
            if self._secure is None and parsed_uri.scheme == "https":
                logger.info(
                    f"URI scheme 是 'https'，将设置 secure=True (别名: {self.alias})。"
                )
                self._secure = True
            elif self._secure is None:
                self._secure = False  # 默认不安全
            self._connection_info["secure"] = self._secure
        elif self._host:
            logger.info(
                f"将使用 Host '{self._host}' 和 Port '{self._port}' 进行连接 (别名: {self.alias})。"
            )
            self._connection_info["host"] = self._host
            self._connection_info["port"] = self._port  # 确保是字符串
            if self._secure is not None:
                self._connection_info["secure"] = self._secure
            else:
                self._connection_info["secure"] = False  # 默认不安全
        else:
            # uri 和 host 都未有效提供（使用默认值或 None）
            # 在 pymilvus < 2.4 中，如果 host 和 uri 都没给，connect 会报错
            # 在 pymilvus >= 2.4 中，connect 可以不带 host/port/uri，使用默认 'localhost:19530'
            # 为了明确性，我们还是倾向于要求至少有 host 或 uri
            # 但为了兼容默认行为，我们可以尝试使用默认值
            logger.warning(
                f"未提供 URI 或 Host，将尝试使用默认 Host '{self._host}' 和 Port '{self._port}' (别名: {self.alias})。"
            )
            self._connection_info["host"] = self._host
            self._connection_info["port"] = self._port
            self._connection_info["secure"] = (
                self._secure if self._secure is not None else False
            )
        # -- 处理认证信息 --
        if self._token:
            # Milvus 2.2.9+ / PyMilvus 2.2.9+
            if (
                hasattr(connections, "connect")
                and "token" in connections.connect.__code__.co_varnames
            ):
                logger.info(f"使用 Token 进行认证 (别名: {self.alias})。")
                self._connection_info["token"] = self._token
            else:
                logger.warning(
                    "当前 PyMilvus 版本可能不支持 Token 认证，将忽略 Token 参数。"
                )
        elif self._user and self._password:
            logger.info(f"使用 User/Password 进行认证 (别名: {self.alias})。")
            self._connection_info["user"] = self._user
            self._connection_info["password"] = self._password
        # -- 处理数据库名称 --
        # Milvus 2.2+ / PyMilvus 2.2+
        if (
            hasattr(connections, "connect")
            and "db_name" in connections.connect.__code__.co_varnames
        ):
            if self._db_name != "default":
                logger.info(f"连接到数据库 '{self._db_name}' (别名: {self.alias})。")
            self._connection_info["db_name"] = self._db_name
        elif self._db_name != "default":
            logger.warning(
                f"当前 PyMilvus 版本可能不支持多数据库，将忽略 db_name='{self._db_name}' 参数。"
            )
        # 合并额外参数，显式参数优先
        self._connection_info.update(self.connect_kwargs)
        # 尝试在初始化时连接
        try:
            self.connect()
        except Exception as e:
            logger.error(f"初始化时连接 Milvus (别名: {self.alias}) 失败: {e}")
            # 允许在连接失败的情况下创建实例

    def connect(self) -> None:
        """建立到 Milvus 服务器的连接。"""
        if self._is_connected:
            logger.info(f"已连接到 Milvus (别名: {self.alias})。")
            return
        logger.info(
            f"尝试连接到 Milvus (别名: {self.alias}) 使用参数: {self._connection_info}"
        )
        try:
            connections.connect(
                alias=self.alias,
                **self._connection_info,  # 使用构建好的参数字典
            )
            self._is_connected = True
            logger.info(f"成功连接到 Milvus (别名: {self.alias})。")
        except MilvusException as e:
            logger.error(f"连接 Milvus (别名: {self.alias}) 失败: {e}")
            self._is_connected = False
            raise
        except Exception as e:  # 捕获其他潜在错误，如网络错误
            logger.error(f"连接 Milvus (别名: {self.alias}) 时发生非 Milvus 异常: {e}")
            self._is_connected = False
            raise ConnectionError(f"连接 Milvus (别名: {self.alias}) 失败: {e}") from e

    def disconnect(self) -> None:
        """断开与 Milvus 服务器的连接。"""
        if not self._is_connected:
            logger.info(f"尚未连接到 Milvus (alias: {self.alias})，无需断开。")
            return
        logger.info(f"尝试断开 Milvus 连接 (alias: {self.alias})。")
        try:
            connections.disconnect(self.alias)
            self._is_connected = False
            logger.info(f"成功断开 Milvus 连接 (alias: {self.alias})。")
        except MilvusException as e:
            logger.error(f"断开 Milvus 连接 (alias: {self.alias}) 时出错: {e}")
            # 即使出错，也假设连接已断开或处于不良状态
            self._is_connected = False
            raise

    def is_connected(self) -> bool:
        """检查当前连接状态。"""
        # 可以添加一个 ping 或类似的操作来验证连接是否仍然活跃
        # utility.get_server_version(using=self.alias) 可以在某种程度上验证
        try:
            # 简单的检查方式是尝试获取服务器版本
            if self._is_connected:
                utility.get_server_version(using=self.alias)
                return True
            return False
        except Exception:
            self._is_connected = False  # 如果检查失败，更新状态
            return False

    def _ensure_connected(self):
        """内部方法，确保在执行操作前已连接。"""
        if not self.is_connected():
            logger.warning(f"Milvus (alias: {self.alias}) 未连接。尝试重新连接...")
            self.connect()  # 尝试重新连接
        if not self._is_connected:
            raise ConnectionError(
                f"无法连接到 Milvus (alias: {self.alias})。请检查连接参数和服务器状态。"
            )

    # --- Collection Management ---
    def has_collection(self, collection_name: str) -> bool:
        """检查指定的集合是否存在。"""
        self._ensure_connected()
        try:
            return utility.has_collection(collection_name, using=self.alias)
        except MilvusException as e:
            logger.error(f"检查集合 '{collection_name}' 是否存在时出错: {e}")
            return False  # 或者重新抛出异常，取决于你的错误处理策略

    def create_collection(
        self, collection_name: str, schema: CollectionSchema, **kwargs
    ) -> Optional[Collection]:
        """
        创建具有给定模式的新集合。
        Args:
            collection_name (str): 要创建的集合的名称。
            schema (CollectionSchema): 定义集合结构的 CollectionSchema 对象。
            **kwargs: 传递给 Collection 构造函数的其他参数 (例如 consistency_level="Strong")。
        Returns:
            Optional[Collection]: 如果成功，则返回 Collection 对象，否则返回 None 或现有集合句柄。
        """
        self._ensure_connected()
        if self.has_collection(collection_name):
            logger.warning(f"集合 '{collection_name}' 已存在。")
            # 返回现有集合的句柄
            try:
                return Collection(name=collection_name, using=self.alias)
            except Exception as e:
                logger.error(f"获取已存在集合 '{collection_name}' 句柄失败: {e}")
                return None

        logger.info(f"尝试创建集合 '{collection_name}'...")
        try:
            # 使用 Collection 类直接创建，它内部会调用 gRPC 创建
            collection = Collection(
                name=collection_name, schema=schema, using=self.alias, **kwargs
            )
            # 显式调用 utility.flush([collection_name]) 可能有助于确保集合元数据更新
            # utility.flush([collection_name], using=self.alias)
            logger.info(f"成功发送创建集合 '{collection_name}' 的请求。")
            return collection
        except MilvusException as e:
            logger.error(f"创建集合 '{collection_name}' 失败: {e}")
            return None  # 或者抛出异常
        except Exception as e:  # 捕获其他可能的错误
            logger.error(f"创建集合 '{collection_name}' 时发生意外错误: {e}")
            return None

    def drop_collection(
        self, collection_name: str, timeout: Optional[float] = None
    ) -> bool:
        """
        删除指定的集合。
        Args:
            collection_name (str): 要删除的集合的名称。
            timeout (Optional[float]): 等待操作完成的超时时间（秒）。
        Returns:
            bool: 如果成功删除则返回 True，否则返回 False。
        """
        self._ensure_connected()
        if not self.has_collection(collection_name):
            logger.warning(f"尝试删除不存在的集合 '{collection_name}'。")
            return True  # 可以认为目标状态已达到
        logger.info(f"尝试删除集合 '{collection_name}'...")
        try:
            utility.drop_collection(collection_name, timeout=timeout, using=self.alias)
            logger.info(f"成功删除集合 '{collection_name}'。")
            return True
        except MilvusException as e:
            logger.error(f"删除集合 '{collection_name}' 失败: {e}")
            return False

    def list_collections(self) -> List[str]:
        """列出 Milvus 实例中的所有集合。"""
        self._ensure_connected()
        try:
            return utility.list_collections(using=self.alias)
        except MilvusException as e:
            logger.error(f"列出集合失败: {e}")
            return []

    def get_collection(self, collection_name: str) -> Optional[Collection]:
        """
        获取指定集合的 Collection 对象句柄。
        Args:
            collection_name (str): 集合名称。
        Returns:
            Optional[Collection]: 如果集合存在，则返回 Collection 对象，否则返回 None 或抛出异常。
        """
        self._ensure_connected()
        if not self.has_collection(collection_name):
            logger.error(f"集合 '{collection_name}' 不存在。")
            # 可以选择抛出 CollectionNotExistException
            # raise CollectionNotExistException(f"Collection '{collection_name}' does not exist.")
            return None
        try:
            # 验证集合确实存在并获取句柄
            collection = Collection(name=collection_name, using=self.alias)
            # 尝试调用一个简单的方法来确认句柄有效，如 describe()
            # 这会验证连接和集合存在性
            collection.describe()
            return collection
        except CollectionNotExistException:  # 再次捕获以防万一
            logger.error(f"获取集合 '{collection_name}' 句柄时确认其不存在。")
            return None
        except MilvusException as e:
            logger.error(f"获取集合 '{collection_name}' 句柄时出错: {e}")
            return None

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        获取集合的统计信息 (例如实体数量)。
        注意：获取准确的行数可能需要先执行 flush 操作。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            return {"error": f"Collection '{collection_name}' not found."}
        try:
            # Milvus 2.2.9+ 推荐使用 utility.get_collection_stats
            # 确保连接有效
            self._ensure_connected()
            # 先 flush 获取最新数据
            self.flush([collection_name])  # 确保统计数据相对最新
            stats = utility.get_collection_stats(
                collection_name=collection_name, using=self.alias
            )
            # stats 返回的是一个包含 'row_count' 等键的字典
            row_count = int(stats.get("row_count", 0))  # 确保是整数
            logger.info(f"获取到集合 '{collection_name}' 的统计信息: {stats}")
            # 返回标准化的字典，包含row_count
            return {"row_count": row_count, **dict(stats)}
        except MilvusException as e:
            logger.error(f"获取集合 '{collection_name}' 统计信息失败: {e}")
            return {"error": str(e)}
        except Exception as e:  # 捕获其他错误
            logger.error(f"获取集合 '{collection_name}' 统计信息时发生意外错误: {e}")
            return {"error": f"Unexpected error: {str(e)}"}

    # --- Data Operations ---
    def insert(
        self,
        collection_name: str,
        data: List[Union[List, Dict]],
        partition_name: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Optional[Any]:
        """
        向指定集合插入数据。
        Args:
            collection_name (str): 目标集合名称。
            data (List[Union[List, Dict]]): 要插入的数据。
                - 如果 schema 字段有序，可以是 List[List]。
                - 推荐使用 List[Dict]，其中 key 是字段名。
            partition_name (Optional[str]): 要插入到的分区名称。
            timeout (Optional[float]): 操作超时时间。
            **kwargs: 传递给 collection.insert 的其他参数。
        Returns:
            Optional[MutationResult]: 包含插入实体的主键 (IDs) 的结果对象，如果失败则返回 None。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            logger.error(f"无法获取集合 '{collection_name}' 以进行插入。")
            return None
        if not data:
            logger.warning(f"尝试向集合 '{collection_name}' 插入空数据列表。")
            return None  # 或者返回一个空的 MutationResult
        logger.info(f"向集合 '{collection_name}' 插入 {len(data)} 条数据...")
        try:
            # 确保 create_time 字段存在且为 INT64 时间戳
            current_timestamp = int(time.time())
            for item in data:
                if isinstance(item, dict) and "create_time" not in item:
                    item["create_time"] = current_timestamp
                # Add more checks if needed (e.g., for List[List])

            mutation_result = collection.insert(
                data=data, partition_name=partition_name, timeout=timeout, **kwargs
            )
            logger.info(
                f"成功向集合 '{collection_name}' 插入数据。PKs: {mutation_result.primary_keys}"
            )
            # 考虑是否在这里自动 flush，或者让调用者决定
            # self.flush([collection_name])
            return mutation_result
        except MilvusException as e:
            logger.error(f"向集合 '{collection_name}' 插入数据失败: {e}")
            return None
        except Exception as e:
            logger.error(f"向集合 '{collection_name}' 插入数据时发生意外错误: {e}")
            return None

    def delete(
        self,
        collection_name: str,
        expression: str,
        partition_name: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Optional[Any]:
        """
        根据布尔表达式删除集合中的实体。
        Args:
            collection_name (str): 目标集合名称。
            expression (str): 删除条件表达式 (例如, "id_field in [1, 2, 3]" 或 "age > 30")。
            partition_name (Optional[str]): 在指定分区内执行删除。
            timeout (Optional[float]): 操作超时时间。
            **kwargs: 传递给 collection.delete 的其他参数。
        Returns:
            Optional[MutationResult]: 包含删除实体的主键 (如果适用) 的结果对象，如果失败则返回 None。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            logger.error(f"无法获取集合 '{collection_name}' 以执行删除。")
            return None
        logger.info(
            f"尝试从集合 '{collection_name}' 中删除满足条件 '{expression}' 的实体..."
        )
        try:
            mutation_result = collection.delete(
                expr=expression,
                partition_name=partition_name,
                timeout=timeout,
                **kwargs,
            )
            delete_count = (
                mutation_result.delete_count
                if hasattr(mutation_result, "delete_count")
                else "N/A"
            )
            logger.info(
                f"成功从集合 '{collection_name}' 发送删除请求。删除数量: {delete_count} (注意: 实际删除需flush后生效)"
            )
            # 考虑是否在这里自动 flush
            # self.flush([collection_name])
            return mutation_result
        except MilvusException as e:
            logger.error(f"从集合 '{collection_name}' 删除实体失败: {e}")
            return None
        except Exception as e:
            logger.error(f"从集合 '{collection_name}' 删除实体时发生意外错误: {e}")
            return None

    def flush(self, collection_names: List[str], timeout: Optional[float] = None):
        """
        将指定集合的内存中的插入/删除操作持久化到磁盘存储。
        这对于确保数据可见性和准确的统计信息很重要。
        Args:
            collection_names (List[str]): 需要刷新的集合名称列表。
            timeout (Optional[float]): 操作超时时间。
        """
        self._ensure_connected()
        if not collection_names:
            logger.warning("Flush 操作需要指定至少一个集合名称。")
            return
        logger.info(f"尝试刷新集合: {collection_names}...")
        try:
            for collection_name in collection_names:
                collection = Collection(collection_name, using=self.alias)
                collection.flush(timeout=timeout)
            # utility.flush(collection_names, timeout=timeout, using=self.alias)
            logger.info(f"成功刷新集合: {collection_names}。")
        except MilvusException as e:
            logger.error(f"刷新集合 {collection_names} 失败: {e}")
            # 根据需要决定是否抛出异常
        except Exception as e:
            logger.error(f"刷新集合 {collection_names} 时发生意外错误: {e}")

    # --- Indexing ---
    def create_index(
        self,
        collection_name: str,
        field_name: str,
        index_params: Dict[str, Any],
        index_name: Optional[str] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> bool:
        """
        在指定集合的字段上创建索引。
        Args:
            collection_name (str): 集合名称。
            field_name (str): 要创建索引的字段名称 (通常是向量字段)。
            index_params (Dict[str, Any]): 索引参数字典。
                必须包含 'metric_type' (e.g., 'L2', 'IP'), 'index_type' (e.g., 'IVF_FLAT', 'HNSW'),
                和 'params' (一个包含索引特定参数的字典, e.g., {'nlist': 1024} 或 {'M': 16, 'efConstruction': 200})。
            index_name (Optional[str]): 索引的自定义名称。
            timeout (Optional[float]): 操作超时时间。
            **kwargs: 传递给 collection.create_index 的其他参数。
        Returns:
            bool: 如果成功创建索引则返回 True，否则返回 False。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            logger.error(f"无法获取集合 '{collection_name}' 以创建索引。")
            return False
        # 检查字段是否存在于 Schema 中
        try:
            field_exists = any(f.name == field_name for f in collection.schema.fields)
            if not field_exists:
                logger.error(
                    f"字段 '{field_name}' 在集合 '{collection_name}' 的 schema 中不存在。"
                )
                return False
        except Exception as e:
            logger.warning(f"检查字段是否存在时出错（可能集合未加载或描述失败）: {e}")
            # 继续尝试创建，让 Milvus 决定

        # 构建默认索引名
        default_index_name = (
            f"_{field_name}_idx"  # PyMilvus 默认可能用 _default_idx 或基于字段
        )
        effective_index_name = index_name if index_name else default_index_name

        # 检查是否已有索引 (使用提供的名称或可能的默认名称)
        try:
            if collection.has_index(index_name=effective_index_name):
                logger.warning(
                    f"集合 '{collection_name}' 的字段 '{field_name}' 上已存在名为 '{effective_index_name}' 的索引。"
                )
                return True  # 认为目标已达成
            # 如果没有指定 index_name，也检查一下是否已存在针对该 field 的索引（名称可能未知）
            elif not index_name and collection.has_index():
                # 进一步检查索引是否在目标字段上
                indices = collection.indexes
                for index in indices:
                    if index.field_name == field_name:
                        logger.warning(
                            f"集合 '{collection_name}' 的字段 '{field_name}' 上已存在索引 (名称: {index.index_name})。"
                        )
                        return True

        except MilvusException as e:
            # 如果 has_index 出错，记录并继续尝试创建
            logger.warning(f"检查索引是否存在时出错: {e}。将继续尝试创建索引。")
        except Exception as e:
            logger.warning(f"检查索引是否存在时发生意外错误: {e}。将继续尝试创建索引。")

        logger.info(
            f"尝试在集合 '{collection_name}' 的字段 '{field_name}' 上创建索引 (名称: {effective_index_name})..."
        )
        try:
            collection.create_index(
                field_name=field_name,
                index_params=index_params,
                index_name=effective_index_name,  # 使用确定好的名称
                timeout=timeout,
                **kwargs,
            )
            # 等待索引构建完成 (重要!)
            logger.info("等待索引构建完成...")
            collection.load()  # 加载是搜索的前提，也隐式触发或等待索引
            utility.wait_for_index_building_complete(
                collection_name, index_name=effective_index_name, using=self.alias
            )
            logger.info(
                f"成功在集合 '{collection_name}' 的字段 '{field_name}' 上创建并构建索引 (名称: {effective_index_name})。"
            )
            return True
        except MilvusException as e:
            logger.error(
                f"为集合 '{collection_name}' 字段 '{field_name}' 创建索引失败: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"为集合 '{collection_name}' 字段 '{field_name}' 创建索引时发生意外错误: {e}"
            )
            return False

    def has_index(self, collection_name: str, index_name: Optional[str] = None) -> bool:
        """检查集合上是否存在索引。"""
        collection = self.get_collection(collection_name)
        if not collection:
            return False
        try:
            return collection.has_index(index_name=index_name, timeout=None)
        except IndexNotExistException:  # 特别捕获索引不存在的异常
            return False
        except MilvusException as e:
            logger.error(
                f"检查集合 '{collection_name}' 的索引 '{index_name or '任意'}' 时出错: {e}"
            )
            return False  # 或者抛出异常
        except Exception as e:
            logger.error(
                f"检查集合 '{collection_name}' 的索引 '{index_name or '任意'}' 时发生意外错误: {e}"
            )
            return False

    def drop_index(
        self,
        collection_name: str,
        field_name: Optional[str] = None,
        index_name: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """删除集合上的索引。优先使用 index_name，如果未提供则尝试基于 field_name 删除（可能删除该字段上的默认索引）。"""
        collection = self.get_collection(collection_name)
        if not collection:
            return False

        effective_index_name = index_name  # 优先使用显式名称

        # 如果没有提供 index_name，尝试查找与 field_name 关联的索引
        if not effective_index_name and field_name:
            try:
                indices = collection.indexes
                found = False
                for index in indices:
                    if index.field_name == field_name:
                        effective_index_name = index.index_name
                        logger.info(
                            f"找到与字段 '{field_name}' 关联的索引: '{effective_index_name}'。"
                        )
                        found = True
                        break
                if not found:
                    logger.warning(
                        f"在集合 '{collection_name}' 中未找到与字段 '{field_name}' 关联的索引，无法删除。"
                    )
                    return True  # 没有对应索引，认为目标达成
            except Exception as e:
                logger.error(
                    f"查找字段 '{field_name}' 的索引时出错: {e}。无法继续删除。"
                )
                return False
        elif not effective_index_name and not field_name:
            logger.error("必须提供 index_name 或 field_name 来删除索引。")
            return False

        # 检查索引是否存在
        try:
            if not collection.has_index(index_name=effective_index_name):
                logger.warning(
                    f"尝试删除不存在的索引（名称: {effective_index_name}）于集合 '{collection_name}'。"
                )
                return True  # 认为目标状态已达到
        except IndexNotExistException:
            logger.warning(
                f"尝试删除不存在的索引（名称: {effective_index_name}）于集合 '{collection_name}'。"
            )
            return True
        except Exception as e:
            logger.warning(
                f"检查索引 '{effective_index_name}' 是否存在时出错: {e}。将继续尝试删除。"
            )

        logger.info(
            f"尝试删除集合 '{collection_name}' 上的索引 (名称: {effective_index_name})..."
        )
        try:
            collection.drop_index(index_name=effective_index_name, timeout=timeout)
            logger.info(
                f"成功删除集合 '{collection_name}' 上的索引 (名称: {effective_index_name})。"
            )
            return True
        except MilvusException as e:
            logger.error(
                f"删除集合 '{collection_name}' 上的索引 '{effective_index_name}' 失败: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"删除集合 '{collection_name}' 上的索引 '{effective_index_name}' 时发生意外错误: {e}"
            )
            return False

    # --- Search & Query ---
    def load_collection(
        self,
        collection_name: str,
        replica_number: int = 1,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> bool:
        """
        将集合加载到内存中以进行搜索。
        Args:
            collection_name (str): 要加载的集合名称。
            replica_number (int): 要加载的副本数量。
            timeout (Optional[float]): 操作超时时间。
            **kwargs: 传递给 collection.load 的其他参数。
        Returns:
            bool: 如果成功加载则返回 True，否则返回 False。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            return False
        # 检查加载状态
        try:
            progress = utility.loading_progress(collection_name, using=self.alias)
            # progress['loading_progress'] 会是 0 到 100 的整数，或 None
            if progress and progress.get("loading_progress") == 100:
                logger.info(f"集合 '{collection_name}' 已加载。")
                return True
        except Exception as e:
            if e.code == 101:  # 集合未加载
                logger.warning(f"集合 '{collection_name}' 尚未加载，将尝试加载。")
            else:
                logger.error(
                    f"检查集合 '{collection_name}' 加载状态时出错: {e}。将尝试加载。"
                )

        logger.info(f"尝试将集合 '{collection_name}' 加载到内存...")
        try:
            collection.load(replica_number=replica_number, timeout=timeout, **kwargs)
            # 检查加载进度/等待完成
            logger.info(f"等待集合 '{collection_name}' 加载完成...")
            utility.wait_for_loading_complete(
                collection_name, using=self.alias, timeout=timeout
            )
            logger.info(f"成功加载集合 '{collection_name}' 到内存。")
            return True
        except MilvusException as e:
            logger.error(f"加载集合 '{collection_name}' 失败: {e}")
            # 常见错误：未创建索引
            if "index not found" in str(e).lower():
                logger.error(
                    f"加载失败原因可能是集合 '{collection_name}' 尚未创建索引。"
                )
            return False
        except Exception as e:
            logger.error(f"加载集合 '{collection_name}' 时发生意外错误: {e}")
            return False

    def release_collection(
        self, collection_name: str, timeout: Optional[float] = None, **kwargs
    ) -> bool:
        """从内存中释放集合。"""
        collection = self.get_collection(collection_name)
        if not collection:
            return False

        # 检查加载状态，如果未加载则无需释放
        try:
            progress = utility.loading_progress(collection_name, using=self.alias)
            if progress and progress.get("loading_progress") == 0:
                logger.info(f"集合 '{collection_name}' 未加载，无需释放。")
                return True
        except Exception as e:
            logger.warning(
                f"检查集合 '{collection_name}' 加载状态时出错: {e}。将尝试释放。"
            )

        logger.info(f"尝试从内存中释放集合 '{collection_name}'...")
        try:
            collection.release(timeout=timeout, **kwargs)
            logger.info(f"成功从内存中释放集合 '{collection_name}'。")
            return True
        except MilvusException as e:
            logger.error(f"释放集合 '{collection_name}' 失败: {e}")
            return False
        except Exception as e:
            logger.error(f"释放集合 '{collection_name}' 时发生意外错误: {e}")
            return False

    def search(
        self,
        collection_name: str,
        query_vectors: List[List[float]],
        vector_field: str,
        search_params: Dict[str, Any],
        limit: int,
        expression: Optional[str] = None,
        output_fields: Optional[List[str]] = None,
        partition_names: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Optional[List[Any]]:  # 返回类型是 List[SearchResult]
        """
        在集合中执行向量相似性搜索。
        Args:
            collection_name (str): 要搜索的集合名称。
            query_vectors (List[List[float]]): 查询向量列表。
            vector_field (str): 要搜索的向量字段名称。
            search_params (Dict[str, Any]): 搜索参数。
                必须包含 'metric_type' (e.g., 'L2', 'IP') 和 'params' (一个包含搜索特定参数的字典, e.g., {'nprobe': 10, 'ef': 100})。
            limit (int): 每个查询向量返回的最相似结果的数量 (top_k)。
            expression (Optional[str]): 用于预过滤的布尔表达式 (例如, "category == 'shoes'").
            output_fields (Optional[List[str]]): 要包含在结果中的字段列表。如果为 None，通常只返回 ID 和距离。
            partition_names (Optional[List[str]]): 要搜索的分区列表。如果为 None，则搜索整个集合。
            timeout (Optional[float]): 操作超时时间。
            **kwargs: 传递给 collection.search 的其他参数 (例如 consistency_level)。
        Returns:
            Optional[List[SearchResult]]: 包含每个查询结果的列表，如果失败则返回 None。
                                        每个 SearchResult 包含多个 Hit 对象。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            logger.error(f"无法获取集合 '{collection_name}' 以执行搜索。")
            return None

        # 确保集合已加载
        if not self.load_collection(
            collection_name, timeout=timeout
        ):  # 尝试加载，如果失败则退出
            logger.error(f"搜索前加载集合 '{collection_name}' 失败。")
            return None

        logger.info(
            f"在集合 '{collection_name}' 中搜索 {len(query_vectors)} 个向量 (字段: {vector_field}, top_k: {limit})..."
        )
        try:
            # 确保 output_fields 包含主键字段，以便后续能获取 ID
            pk_field_name = collection.schema.primary_field.name
            if output_fields and pk_field_name not in output_fields:
                output_fields_with_pk = output_fields + [pk_field_name]
            elif not output_fields:
                # 如果 output_fields 为 None, Milvus 默认会返回 ID 和 distance
                output_fields_with_pk = None  # Let Milvus handle default
            else:
                output_fields_with_pk = output_fields

            search_result = collection.search(
                data=query_vectors,
                anns_field=vector_field,
                param=search_params,
                limit=limit,
                expr=expression,
                output_fields=output_fields_with_pk,  # 使用列表可能包括PK
                partition_names=partition_names,
                timeout=timeout,
                **kwargs,
            )
            # search_result is List[SearchResult]
            # 每个SearchResult对应一个query_vector
            # 每个搜索结果都包含一个命中列表
            num_results = len(search_result) if search_result else 0
            logger.info(f"搜索完成。返回 {num_results} 组结果。")

            # # 示例：记录第一个查询的命中数
            # if search_result and len(search_result[0]) > 0:
            #     logger.debug(f"第一个查询向量命中 {len(search_result[0])} 个结果。")
            # logger.debug(f"第一个结果示例 - ID: {search_result[0][0].id}, 距离: {search_result[0][0].distance}")

            return search_result  # 返回原始的 SearchResult 列表
        except MilvusException as e:
            logger.error(f"在集合 '{collection_name}' 中搜索失败: {e}")
            return None
        except Exception as e:
            logger.error(f"在集合 '{collection_name}' 中搜索时发生意外错误: {e}")
            return None

    def query(
        self,
        collection_name: str,
        expression: str,
        output_fields: Optional[List[str]] = None,
        partition_names: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Optional[List[Dict]]:
        """
        根据标量字段过滤条件查询实体。
        Args:
            collection_name (str): 目标集合名称。
            expression (str): 过滤条件表达式 (e.g., "book_id in [100, 200]" or "word_count > 1000").
            output_fields (Optional[List[str]]): 要返回的字段列表。如果为 None，通常返回所有标量字段和主键。
                                            可以包含 '*' 来获取所有字段（包括向量，可能很大）。
            partition_names (Optional[List[str]]): 在指定分区内查询。
            limit (Optional[int]): 返回的最大实体数。Milvus 对 query 的 limit 有上限 (e.g., 16384)，需注意。
            offset (Optional[int]): 返回结果的偏移量（用于分页）。
            timeout (Optional[float]): 操作超时时间。
             **kwargs: 传递给 collection.query 的其他参数 (例如 consistency_level)。
        Returns:
            Optional[List[Dict]]: 满足条件的实体列表 (每个实体是一个字典)，如果失败则返回 None。
        """
        collection = self.get_collection(collection_name)
        if not collection:
            logger.error(f"无法获取集合 '{collection_name}' 以执行查询。")
            return None

        # Query 不需要集合预先加载到内存，但需要连接
        self._ensure_connected()

        # Milvus 对 query 的 limit 有内部限制，如果传入的 limit 过大，可能需要分批查询或调整
        # 默认可能是 16384，检查 pymilvus 文档或 Milvus 配置
        effective_limit = limit
        # if limit and limit > 16384:
        #     logger.warning(f"查询 limit {limit} 可能超过 Milvus 内部限制 (通常为 16384)，结果可能被截断。")
        #     # effective_limit = 16384 # 或者根据需要处理分页

        logger.info(
            f"在集合 '{collection_name}' 中执行查询: '{expression}' (Limit: {effective_limit}, Offset: {offset})..."
        )
        try:
            # 确保 output_fields 包含主键，因为 query 结果默认可能不含（与 search 不同）
            pk_field_name = collection.schema.primary_field.name
            if (
                output_fields
                and pk_field_name not in output_fields
                and "*" not in output_fields
            ):
                query_output_fields = output_fields + [pk_field_name]
            elif not output_fields:
                # 如果 None, 尝试获取所有非向量字段 + PK
                query_output_fields = [
                    f.name
                    for f in collection.schema.fields
                    if f.dtype != DataType.FLOAT_VECTOR
                    and f.dtype != DataType.BINARY_VECTOR
                ]
                if pk_field_name not in query_output_fields:
                    query_output_fields.append(pk_field_name)
            else:  # Already contains PK or '*'
                query_output_fields = output_fields

            query_results = collection.query(
                expr=expression,
                output_fields=query_output_fields,
                partition_names=partition_names,
                limit=effective_limit,  # Use potentially adjusted limit
                offset=offset,
                timeout=timeout,
                **kwargs,
            )
            # query_results is List[Dict]
            logger.info(f"查询完成。返回 {len(query_results)} 个实体。")
            return query_results
        except MilvusException as e:
            logger.error(f"在集合 '{collection_name}' 中执行查询失败: {e}")
            return None
        except Exception as e:
            logger.error(f"在集合 '{collection_name}' 中执行查询时发生意外错误: {e}")
            return None

    # --- Context Manager Support ---
    def __enter__(self):
        """支持 with 语句，进入时确保连接。"""
        try:
            self.connect()  # 确保连接，如果失败会抛异常
        except Exception as e:
            logger.error(f"进入 MilvusManager 上下文管理器时连接失败: {e}")
            raise  # 重新抛出异常，阻止进入 with 块
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句，退出时断开连接。"""
        self.disconnect()
        # 可以根据 exc_type 等参数决定是否记录异常信息
        if exc_type:
            logger.error(
                f"MilvusManager 上下文管理器退出时捕获到异常: {exc_type.__name__}: {exc_val}"
            )
        # 返回 False 表示如果发生异常，不抑制异常的传播
