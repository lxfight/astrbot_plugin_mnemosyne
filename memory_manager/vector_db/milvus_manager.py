import os
import pathlib
from typing import List, Dict, Optional, Any, Union
from urllib.parse import urlparse
import time
import sys
from pathlib import Path

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

# 导入安全工具
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from core.security_utils import validate_safe_path
except ImportError:
    # 如果导入失败，定义一个基本的路径验证函数
    def validate_safe_path(file_path: str, base_dir: str, allow_creation: bool = True) -> Path:
        """基本的路径验证函数（后备方案）"""
        base = Path(base_dir).resolve()
        if Path(file_path).is_absolute():
            target = Path(file_path).resolve()
        else:
            target = (base / file_path).resolve()
        
        try:
            target.relative_to(base)
        except ValueError:
            raise ValueError(f"路径遍历检测: 路径试图访问基础目录之外的位置")
        
        if allow_creation and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        
        return target


class MilvusManager:
    """
    一个用于管理与 Milvus 数据库交互的类。
    封装了连接、集合管理、数据操作、索引和搜索等常用功能。
    支持连接到标准 Milvus 服务器 (通过 URI 或 host/port) 或使用 Milvus Lite (通过本地路径)。

    连接优先级:
    1. 如果提供了 `lite_path`，则使用 Milvus Lite 模式。
    2. 如果提供了网络 `uri` (http/https)，则使用标准网络连接。
    3. 如果提供了显式的 `host` (非 'localhost')，则使用 host/port 连接。
    4. 如果以上都未提供，则默认使用 Milvus Lite，数据路径为当前文件向上追溯4层的目录下的 `milvus_data/default_milvus_lite.db`
    """

    def __init__(
        self,
        alias: str = "default",
        lite_path: Optional[str] = None,
        uri: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[Union[str, int]] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        secure: Optional[bool] = None,
        token: Optional[str] = None,
        db_name: str = "default",
        **kwargs,
    ):
        """
        初始化 MilvusManager。

        Args:
            # 参数说明与之前保持一致
            alias (str): 此连接的别名。
            lite_path (Optional[str]): Milvus Lite 数据文件的本地路径。优先使用。
            uri (Optional[str]): 标准 Milvus 连接 URI (http/https)。
            host (Optional[str]): Milvus 服务器主机名/IP。
            port (Optional[Union[str, int]]): Milvus 服务器端口。
            user (Optional[str]): 标准 Milvus 认证用户名。
            password (Optional[str]): 标准 Milvus 认证密码。
            secure (Optional[bool]): 是否对标准 Milvus 连接使用 TLS/SSL。
            token (Optional[str]): 标准 Milvus 认证 Token/API Key。
            db_name (str): 要连接的数据库名称 (Milvus 2.2+)。
            **kwargs: 传递给 connections.connect 的其他参数。
        """

        self.alias = alias
        self._original_lite_path = lite_path  # 保留原始输入以供参考
        self._lite_path = (
            self._prepare_lite_path(lite_path) if lite_path is not None else None
        )

        self._uri = uri

        self._host = host
        self._raw_host = host
        self._port = str(port) if port is not None else "19530"

        self._user = user
        self._password = password
        self._secure = secure
        self._token = token
        self._db_name = db_name

        self.connect_kwargs = kwargs  # 存储额外的连接参数

        self._connection_info = {}  # 用于存储最终传递给 connect 的参数
        self._is_connected = False
        self._is_lite = False  # 标志是否为 Lite 模式
        self._last_connection_check = 0  # 上次连接检查时间戳
        self._connection_check_interval = 30  # 连接检查间隔（秒）
        self._cached_connection_status = False  # 缓存的连接状态

        # 3. 确定连接模式并配置参数
        self._configure_connection_mode()

        # 4. 添加通用配置 (如 db_name)
        self._add_common_config()

        # 5. 合并额外的 kwargs 参数
        self._merge_kwargs()

        # 6. 尝试建立初始连接
        self._attempt_initial_connect()

    # ------- 私有方法 -------
    def _prepare_lite_path(self, path_input: str) -> str:
        """
        准备 Milvus Lite 路径。如果输入路径不是以 .db 结尾，
        则假定为目录，并在其后附加默认文件名。
        返回安全验证后的绝对路径。
        
        Args:
            path_input: 输入的路径
            
        Returns:
            str: 安全验证后的绝对路径
            
        Raises:
            ValueError: 如果路径不安全（路径遍历攻击）
        """
        # 标准化路径分隔符
        path_input = os.path.normpath(path_input)
        _, ext = os.path.splitext(path_input)

        final_path = path_input
        if ext.lower() != ".db":
            # 不是以 .db 结尾，假设是目录或基名，附加默认文件名
            final_path = os.path.join(path_input, "mnemosyne_lite.db")
            logger.info(
                f"提供的 lite_path '{path_input}' 未以 '.db' 结尾。假定为目录/基名，自动附加默认文件名 'mnemosyne_lite.db'。"
            )

        # 计算基础目录（当前文件向上4层）
        try:
            current_file_path = pathlib.Path(__file__).resolve()
            base_dir = current_file_path.parents[4]
            default_data_dir = base_dir / "mnemosyne_data"
        except IndexError:
            # 如果无法获取上层目录，使用当前工作目录
            default_data_dir = pathlib.Path.cwd() / "mnemosyne_data"
            logger.warning(f"无法获取基础目录，使用当前工作目录: {default_data_dir}")
        
        # 安全验证路径，防止路径遍历攻击
        try:
            safe_path = validate_safe_path(
                final_path,
                str(default_data_dir),
                allow_creation=True
            )
            absolute_path = str(safe_path)
            logger.debug(f"路径安全验证通过，最终处理后的 Milvus Lite 绝对路径: '{absolute_path}'")
            return absolute_path
        except ValueError as e:
            logger.error(f"Milvus Lite 路径安全验证失败: {e}")
            raise ValueError(f"不安全的 Milvus Lite 路径: {path_input}。{e}") from e

    def _configure_connection_mode(self):
        """根据输入参数决定连接模式并调用相应的配置方法。"""
        # 注意：这里的 self._lite_path 已经是经过 _prepare_lite_path 处理后的完整路径
        if self._lite_path is not None:
            self._configure_lite_explicit()
        elif self._uri and urlparse(self._uri).scheme in ["http", "https"]:
            self._configure_uri()
        # 检查 host 是否显式提供且不是 'localhost' (忽略大小写)
        elif self._host is not None and self._host.lower() != "localhost":
            self._configure_host_port()
        else:
            self._configure_lite_default()  # 默认模式也应该使用 _prepare_lite_path 计算路径

    def _ensure_db_dir_exists(self, db_path: str):
        """确保 Milvus Lite 数据库文件所在的目录存在。"""
        # db_path 已经是绝对路径
        db_dir = os.path.dirname(db_path)
        if not os.path.exists(db_dir):  # 检查目录是否存在
            try:
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"为 Milvus Lite 创建了目录: '{db_dir}'")
            except OSError as e:
                logger.error(
                    f"无法为 Milvus Lite 创建目录 '{db_dir}': {e}。请检查权限。"
                )
                # 也许应该在这里抛出异常，因为无法创建目录会导致连接失败
                # raise OSError(f"无法为 Milvus Lite 创建目录 '{db_dir}': {e}") from e
            except Exception as e:  # 捕获其他潜在错误
                logger.error(
                    f"尝试为 Milvus Lite 创建目录 '{db_dir}' 时发生意外错误: {e}。"
                )
                # raise # 重新抛出，让上层知道出错了

    def _get_default_lite_path(self) -> str:
        """计算默认的 Milvus Lite 数据路径（当前文件上4层目录）。"""
        try:
            # 获取定义 MilvusManager 类的文件的绝对路径
            current_file_path = pathlib.Path(__file__).resolve()
            # parents[0] 是当前目录, parents[1] 是上一层, ..., parents[3] 是上四层
            base_dir = current_file_path.parents[4]
            # 在该目录下创建一个子目录存放数据
            default_dir = base_dir / "mnemosyne_data"
            # 使用 _prepare_lite_path 来确保最终路径是带 .db 的文件路径
            default_path = self._prepare_lite_path(str(default_dir))
            logger.info(f"动态计算的默认 Milvus Lite 路径为: '{default_path}'")
            return default_path
        except IndexError:
            # 使用当前工作目录下的默认文件名
            fallback_dir = "."
            fallback_path = self._prepare_lite_path(fallback_dir)
            logger.warning(
                f"无法获取当前文件 '{__file__}' 的上4层目录结构，"
                f"将使用当前工作目录下的 '{fallback_path}' 作为默认 Milvus Lite 路径。"
            )
            return fallback_path
        except Exception as e:
            fallback_dir = "."
            fallback_path = self._prepare_lite_path(fallback_dir)
            logger.error(
                f"计算默认 Milvus Lite 路径时发生意外错误: {e}，"
                f"将使用当前工作目录下的 '{fallback_path}' 作为默认路径。"
            )
            return fallback_path

    def _configure_lite_explicit(self):
        """配置使用显式指定的 Milvus Lite 路径。"""
        self._is_lite = True
        # self._lite_path 在 __init__ 中已通过 _prepare_lite_path 处理
        logger.info(
            f"配置 Milvus Lite (别名: {self.alias})。原始输入路径: '{self._original_lite_path}', 最终数据文件路径: '{self._lite_path}'"
        )

        # 确保目录存在（基于最终的文件路径）
        self._ensure_db_dir_exists(self._lite_path)

        # 使用处理后的完整文件路径作为 URI
        self._connection_info["uri"] = self._lite_path
        logger.warning(
            "在 Milvus Lite (显式路径) 模式下，将忽略 host, port, secure, user, password, token 参数。"
        )

    def _configure_lite_default(self):
        """配置使用默认的 Milvus Lite 路径。"""
        self._is_lite = True
        # 调用 _get_default_lite_path 获取已处理好的默认文件路径
        default_lite_path = self._get_default_lite_path()
        logger.warning(
            f"未提供明确连接方式，将默认使用 Milvus Lite (别名: {self.alias})。数据文件路径: '{default_lite_path}'"
        )

        # 确保目录存在（基于最终的文件路径）
        self._ensure_db_dir_exists(default_lite_path)

        # 使用处理后的完整文件路径作为 URI
        self._connection_info["uri"] = default_lite_path
        logger.warning(
            "在默认 Milvus Lite 模式下，将忽略 host, port, secure, user, password, token 参数。"
        )

    def _configure_uri(self):
        """配置使用标准网络 URI 连接。"""
        self._is_lite = False
        logger.info(f"配置标准 Milvus (别名: {self.alias}) 使用 URI: '{self._uri}'。")
        self._connection_info["uri"] = self._uri
        parsed_uri = urlparse(self._uri)

        # 处理认证 (Token 优先)
        if self._token:
            self._add_token_auth("URI")
        elif self._user and self._password:
            self._add_user_password_auth("URI")
        elif parsed_uri.username and parsed_uri.password:  # 从 URI 提取
            logger.info(f"从 URI 中提取 User/Password 进行认证 (别名: {self.alias})。")
            self._connection_info["user"] = parsed_uri.username
            self._connection_info["password"] = parsed_uri.password

        # 处理 secure
        if self._secure is None:  # 如果未显式设置
            self._secure = parsed_uri.scheme == "https"
            logger.info(
                f"根据 URI scheme ('{parsed_uri.scheme}') 推断 secure={self._secure} (别名: {self.alias})。"
            )
        else:
            logger.info(
                f"使用显式设置的 secure={self._secure} (URI 连接, 别名: {self.alias})。"
            )
        self._connection_info["secure"] = self._secure

    def _configure_host_port(self):
        """配置使用 Host/Port 连接标准 Milvus。"""
        self._is_lite = False
        # host 已在 _configure_connection_mode 中检查过不为 None 且非 'localhost'
        logger.info(
            f"配置标准 Milvus (别名: {self.alias}) 使用 Host: '{self._host}', Port: '{self._port}'。"
        )
        self._connection_info["host"] = self._host
        self._connection_info["port"] = self._port

        # 处理认证 (Token 优先)
        if self._token:
            self._add_token_auth("Host/Port")
        elif self._user and self._password:
            self._add_user_password_auth("Host/Port")

        # 处理 secure
        if self._secure is not None:
            self._connection_info["secure"] = self._secure
            logger.info(
                f"使用显式设置的 secure={self._secure} (Host/Port 连接, 别名: {self.alias})。"
            )
        else:
            self._connection_info["secure"] = False  # 默认不安全
            logger.info(
                f"未设置 secure，默认为 False (Host/Port 连接, 别名: {self.alias})。"
            )

    def _add_token_auth(self, context: str):
        """辅助方法：添加 Token 认证信息。"""
        if (
            hasattr(connections, "connect")
            and "token" in connections.connect.__code__.co_varnames
        ):
            logger.info(f"使用 Token 进行认证 ({context} 连接, 别名: {self.alias})。")
            self._connection_info["token"] = self._token
        else:
            logger.warning(
                f"当前 PyMilvus 版本可能不支持 Token 认证，将忽略 Token 参数 ({context} 连接)。"
            )

    def _add_user_password_auth(self, context: str):
        """辅助方法：添加 User/Password 认证信息。"""
        logger.info(
            f"使用提供的 User/Password 进行认证 ({context} 连接, 别名: {self.alias})。"
        )
        self._connection_info["user"] = self._user
        self._connection_info["password"] = self._password

    def _add_common_config(self):
        """添加对所有连接模式都可能适用的通用配置，如 db_name。"""
        # 处理 db_name (Milvus 2.2+, 对 Lite 和 Standard 都有效)
        if (
            hasattr(connections, "connect")
            and "db_name" in connections.connect.__code__.co_varnames
        ):
            if self._db_name != "default":
                logger.info(f"将连接到数据库 '{self._db_name}' (别名: {self.alias})。")
                self._connection_info["db_name"] = self._db_name
            # else: 不需要记录使用默认库
        elif self._db_name != "default":
            mode_name = "Milvus Lite" if self._is_lite else "Standard Milvus"
            logger.warning(
                f"当前 PyMilvus 版本可能不支持多数据库，将忽略 db_name='{self._db_name}' (模式: {mode_name})。"
            )

        # 注意：alias 不放入 _connection_info，它是 connections.connect 的独立参数

    def _merge_kwargs(self):
        """合并用户传入的额外 kwargs 参数，让显式参数优先。"""
        # final_kwargs = self.connect_kwargs.copy()
        # final_kwargs.update(self._connection_info) # 让 _connection_info 的设置优先
        # self._connection_info = final_kwargs
        # 改为： 让kwargs补充，不覆盖已设置的参数
        for key, value in self.connect_kwargs.items():
            if key not in self._connection_info:
                self._connection_info[key] = value
            else:
                logger.warning(
                    f"忽略 kwargs 中的参数 '{key}'，因为它已被显式参数或内部逻辑设置。"
                )

    def _attempt_initial_connect(self):
        """尝试在初始化时建立连接。"""
        try:
            self.connect()
        except Exception as e:
            mode = "Milvus Lite" if self._is_lite else "Standard Milvus"
            logger.error(
                f"初始化时连接 {mode} (别名: {self.alias}) 失败: {e}", exc_info=True
            )
            # 允许在连接失败的情况下创建实例，后续操作会尝试重连或报错

    # ------- 公共方法 -------
    def connect(self) -> None:
        """建立到 Milvus 的连接 (根据初始化时确定的模式)。"""
        if self._is_connected:
            mode = "Milvus Lite" if self._is_lite else "Standard Milvus"
            logger.info(f"已连接到 {mode} (别名: {self.alias})。")
            return

        mode = "Milvus Lite" if self._is_lite else "Standard Milvus"
        # 从 _connection_info 中移除 alias，因为它要作为 connect 的第一个参数
        connect_params = self._connection_info.copy()

        logger.info(
            f"尝试连接到 {mode} (别名: {self.alias}) 使用参数: {connect_params}"
        )
        try:
            connections.connect(
                **{"alias": self.alias, **connect_params}
            )  # Works for pymilvus >= 2.4
            self._is_connected = True
            logger.info(f"成功连接到 {mode} (别名: {self.alias})。")
        except MilvusException as e:
            logger.error(f"连接 {mode} (别名: {self.alias}) 失败: {e}")
            self._is_connected = False
            raise  # 保留原始异常类型
        except (ConnectionError, OSError, TimeoutError) as e:  # 捕获其他潜在错误
            logger.error(f"连接 {mode} (别名: {self.alias}) 时发生非 Milvus 异常: {e}")
            self._is_connected = False
            # 将其包装成更通用的连接错误可能更好
            raise ConnectionError(f"连接 {mode} (别名: {self.alias}) 失败: {e}") from e

    def disconnect(self) -> None:
        """断开与 Milvus 服务器或 Lite 实例的连接。"""
        if not self._is_connected:
            logger.info(f"尚未连接到 Milvus (别名: {self.alias})，无需断开。")
            return
        mode = "Milvus Lite" if self._is_lite else "Standard Milvus"
        logger.info(f"尝试断开 {mode} 连接 (别名: {self.alias})。")
        try:
            connections.disconnect(self.alias)
            self._is_connected = False
            logger.info(f"成功断开 {mode} 连接 (别名: {self.alias})。")
        except MilvusException as e:
            logger.error(f"断开 {mode} 连接 (别名: {self.alias}) 时出错: {e}")
            self._is_connected = False  # 即使出错，也标记为未连接
            raise
        except (ConnectionError, OSError) as e:
            logger.error(f"断开 {mode} 连接 (别名: {self.alias}) 时发生意外错误: {e}")
            self._is_connected = False
            raise

    def check_connection(self) -> bool:
        """
        专门的轻量级连接检查方法，使用缓存机制避免频繁检查。
        
        Returns:
            bool: 连接是否正常
        """
        current_time = time.time()
        
        # 如果距离上次检查时间不足间隔时间，返回缓存状态
        if current_time - self._last_connection_check < self._connection_check_interval:
            return self._cached_connection_status
        
        # 执行实际连接检查
        if not self._is_connected:
            self._cached_connection_status = False
            self._last_connection_check = current_time
            return False

        if self._is_lite:
            # Milvus Lite 是本地文件，连接通常更稳定
            self._cached_connection_status = True
            self._last_connection_check = current_time
            return True
        else:
            # 对于标准 Milvus 网络连接，执行轻量级检查
            try:
                # 使用 list_collections 作为轻量级 ping 操作
                utility.list_collections(using=self.alias)
                self._cached_connection_status = True
                self._last_connection_check = current_time
                return True
            except MilvusException as e:
                logger.warning(
                    f"Standard Milvus 连接检查失败 (alias: {self.alias}): {e}"
                )
                self._is_connected = False
                self._cached_connection_status = False
                self._last_connection_check = current_time
                return False
            except Exception as e:
                logger.warning(
                    f"Standard Milvus 连接检查时发生意外错误 (alias: {self.alias}): {e}"
                )
                self._is_connected = False
                self._cached_connection_status = False
                self._last_connection_check = current_time
                return False

    def is_connected(self) -> bool:
        """检查当前连接状态 (使用 has_collection 作为 ping)。"""
        if not self._is_connected:
            return False

        if self._is_lite:
            # Milvus Lite 是本地文件，连接通常更稳定，简单返回标志即可
            return True
        else:
            # 对于标准 Milvus 网络连接，使用专门的连接检查方法
            return self.check_connection()

    def _ensure_connected(self):
        """内部方法，确保在执行操作前已连接。"""
        if not self.is_connected():
            mode = "Milvus Lite" if self._is_lite else "Standard Milvus"
            logger.warning(f"{mode} (别名: {self.alias}) 未连接。尝试重新连接...")
            try:
                self.connect()  # 尝试重新连接
            except Exception as conn_err:
                # 如果重连失败，is_connected 仍然是 False
                logger.error(f"重新连接 {mode} (别名: {self.alias}) 失败: {conn_err}")
                raise ConnectionError(
                    f"无法连接到 {mode} (别名: {self.alias})。请检查连接参数和实例状态。"
                ) from conn_err

        # 再次检查以防万一 connect() 内部逻辑问题
        if not self._is_connected:
            mode = "Milvus Lite" if self._is_lite else "Standard Milvus"
            raise ConnectionError(
                f"未能建立到 {mode} (别名: {self.alias}) 的连接。请检查配置。"
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
            # collection.describe()
            return collection
        except (
            CollectionNotExistException
        ):  # 如果 has_collection 和 Collection 构造之间状态变化
            logger.warning(
                f"获取集合 '{collection_name}' 句柄时发现其不存在 (可能刚被删除)。"
            )
            return None
        except MilvusException as e:
            logger.error(f"获取集合 '{collection_name}' 句柄时出错: {e}")
            return None
        except Exception as e:
            logger.error(f"获取集合 '{collection_name}' 句柄时发生意外错误: {e}")
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
            # M20 修复: 改进时间戳处理，避免覆盖用户提供的有效时间戳
            current_timestamp = int(time.time())
            for item in data:
                if isinstance(item, dict):
                    # 检查是否已有 create_time 字段
                    if "create_time" not in item:
                        # 字段不存在，添加当前时间戳
                        item["create_time"] = current_timestamp
                    else:
                        # 字段存在，验证其格式是否有效
                        existing_time = item.get("create_time")
                        if not isinstance(existing_time, (int, float)):
                            # 无效格式，记录警告并替换
                            logger.warning(
                                f"实体包含无效的 create_time 格式 (类型: {type(existing_time).__name__})，"
                                f"将使用当前时间戳替换"
                            )
                            item["create_time"] = current_timestamp
                        elif existing_time <= 0:
                            # 时间戳为负数或零，无效
                            logger.warning(
                                f"实体包含无效的 create_time 值 ({existing_time})，将使用当前时间戳替换"
                            )
                            item["create_time"] = current_timestamp
                        # else: 用户提供的时间戳有效，保留不变
                # Add more checks if needed (e.g., for List[List])

            mutation_result = collection.insert(
                data=data, partition_name=partition_name, timeout=timeout, **kwargs
            )
            logger.info(
                f"成功向集合 '{collection_name}' 插入数据。PKs: {mutation_result.primary_keys}"
            )
            # 考虑是否在这里自动 flush，或者让调用者决定
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
            self.flush([collection_name])
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
            logger.info(f"成功刷新集合: {collection_names}。")
        except MilvusException as e:
            logger.error(f"刷新集合 {collection_names} 失败: {e}")
            # 根据需要决定是否抛出异常
        except Exception as e:
            logger.error(f"刷新集合 {collection_names} 时发生意外错误: {e}")
        return

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
        except (MilvusException, ConnectionError, TimeoutError) as e:
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
            self._ensure_connected()  # 确保连接，如果失败会抛异常
        except Exception as e:
            logger.error(f"进入 MilvusManager 上下文管理器时连接失败: {e}")
            raise  # 重新抛出异常，阻止进入 with 块
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句，退出时断开连接。"""
        try:
            self.disconnect()
        except Exception as e:
            logger.error(f"退出 MilvusManager 上下文管理器时断开连接失败: {e}")
        # 可以根据 exc_type 等参数决定是否记录异常信息
        if exc_type:
            logger.error(
                f"MilvusManager 上下文管理器退出时捕获到异常: {exc_type.__name__}: {exc_val}"
            )
        # 返回 False 表示如果发生异常，不抑制异常的传播

    def get_connection_info(self) -> Dict[str, Any]:
        """
        返回当前连接信息用于调试
        
        Returns:
            Dict[str, Any]: 包含连接信息的字典，包括：
                - alias: 连接别名
                - is_connected: 是否已连接
                - is_lite: 是否为 Lite 模式
                - connection_params: 连接参数（不包含敏感信息）
                - last_check_time: 上次连接检查时间戳
        """
        # 创建不包含敏感信息的连接参数副本
        safe_connection_info = {}
        for key, value in self._connection_info.items():
            if key in ['password', 'token']:
                safe_connection_info[key] = '******' if value else None
            else:
                safe_connection_info[key] = value
        
        return {
            'alias': self.alias,
            'is_connected': self._is_connected,
            'is_lite': self._is_lite,
            'connection_params': safe_connection_info,
            'last_check_time': self._last_connection_check,
            'connection_check_interval': self._connection_check_interval,
            'cached_connection_status': self._cached_connection_status
        }

    def format_search_results(self, raw_results) -> List[Dict[str, Any]]:
        """
        格式化搜索结果为统一格式
        
        Args:
            raw_results: Milvus 搜索返回的原始结果 (List[SearchResult])
            
        Returns:
            List[Dict[str, Any]]: 格式化后的搜索结果列表，每个元素包含：
                - id: 实体 ID
                - distance: 相似度距离
                - score: 相似度分数 (1 - distance，适用于 L2 距离)
                - entity: 实体数据字典
        """
        if not raw_results:
            return []
        
        formatted_results = []
        
        try:
            # raw_results 是 List[SearchResult]，每个 SearchResult 对应一个查询向量
            for search_result in raw_results:
                # 每个 SearchResult 包含多个 Hit 对象
                for hit in search_result:
                    # 检查 hit 对象是否包含必要属性
                    if not all(hasattr(hit, attr) for attr in ["id", "distance", "entity"]):
                        logger.warning(f"搜索结果对象缺少必要属性: {hit}")
                        continue
                    
                    try:
                        # 获取实体数据
                        entity_dict = {}
                        if hasattr(hit.entity, "to_dict"):
                            entity_dict = hit.entity.to_dict()
                        elif hasattr(hit.entity, "__dict__"):
                            entity_dict = vars(hit.entity)
                        else:
                            # 尝试将实体转换为字典
                            try:
                                entity_dict = dict(hit.entity)
                            except (TypeError, ValueError):
                                logger.warning(f"无法将实体转换为字典: {hit.entity}")
                                entity_dict = {}
                        
                        # 计算相似度分数 (对于 L2 距离，分数越高越相似)
                        distance = float(hit.distance)
                        score = 1.0 / (1.0 + distance)  # 转换为 0-1 范围的分数
                        
                        formatted_result = {
                            "id": hit.id,
                            "distance": distance,
                            "score": score,
                            "entity": entity_dict
                        }
                        
                        formatted_results.append(formatted_result)
                        
                    except Exception as e:
                        logger.error(f"处理单个搜索结果时出错: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"格式化搜索结果时出错: {e}")
            return []
        
        return formatted_results
