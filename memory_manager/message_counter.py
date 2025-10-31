import sqlite3
import os
import threading
from typing import Optional
from pathlib import Path

from astrbot.core.log import LogManager
from astrbot.api.star import StarTools

logging = LogManager.GetLogger(log_name="Message Counter")

# 导入安全工具
import sys
# 添加父目录到路径以便导入 core 模块
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
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


class MessageCounter:
    """
    消息计数器类，使用 SQLite 存储每个会话的消息轮次计数。
    
    优化说明 (Phase 1 - P0):
    - 实现持久数据库连接，避免每次操作创建新连接
    - 添加线程锁确保线程安全
    - 实现连接健康检查和自动重连
    - 支持上下文管理器和资源清理
    """

    def __init__(self, db_file: Optional[str] = None, plugin_data_dir: Optional[str] = None):
        """
        初始化消息计数器，使用 SQLite 数据库存储。
        db_file 参数现在是可选的。如果为 None，则自动使用数据目录生成路径。

        Args:
            db_file (str, optional): SQLite 数据库文件路径。
                                     如果为 None，则使用标准插件数据目录。
            plugin_data_dir (str, optional): 插件数据目录。如果提供，将直接使用此目录。
                                             如果不提供，将尝试使用 StarTools.get_data_dir()。

        Raises:
            ValueError: 如果提供的路径不安全（路径遍历攻击）
        """
        # 确定默认数据目录
        if plugin_data_dir:
            # 外部提供了数据目录，直接使用
            default_data_dir = Path(plugin_data_dir)
            logging.debug(f"使用外部提供的插件数据目录: {default_data_dir}")
        else:
            # 尝试使用 StarTools.get_data_dir() 获取插件数据目录
            try:
                default_data_dir = Path(StarTools.get_data_dir())
                logging.debug(f"使用 StarTools 获取的插件数据目录: {default_data_dir}")
            except RuntimeError as e:
                # 获取失败，使用当前工作目录下的默认位置
                logging.warning(f"无法通过 StarTools 获取数据目录: {e}，将使用默认路径")
                default_data_dir = Path.cwd() / "mnemosyne_data"

        if db_file is None:
            # 使用标准插件数据目录
            default_data_dir.mkdir(parents=True, exist_ok=True)
            self.db_file = str(default_data_dir / "message_counters.db")
            logging.debug(f"使用标准插件数据目录: {self.db_file}")
        else:
            # 安全验证用户提供的路径，防止路径遍历攻击
            try:
                # 验证路径安全性
                safe_path = validate_safe_path(
                    db_file,
                    str(default_data_dir),
                    allow_creation=True
                )
                self.db_file = str(safe_path)
                logging.info(f"使用用户指定的安全数据库路径: {self.db_file}")
            except ValueError as e:
                logging.error(f"数据库路径验证失败: {e}")
                raise ValueError(f"不安全的数据库路径: {db_file}。{e}") from e

        # P0 优化: 持久连接和线程安全
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()  # 线程锁，确保并发安全
        self._closed = False

        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取或创建持久数据库连接。
        
        P0 优化: 使用持久连接替代每次操作创建新连接
        包含连接健康检查和自动重连机制
        
        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        if self._closed:
            raise RuntimeError("MessageCounter 已关闭，无法获取连接")
            
        if self._connection is None:
            try:
                self._connection = sqlite3.connect(
                    self.db_file,
                    check_same_thread=False,  # 允许多线程使用
                    timeout=10.0  # 设置超时避免死锁
                )
                # 启用 WAL 模式以提升并发性能
                self._connection.execute("PRAGMA journal_mode=WAL")
                logging.debug(f"创建新的持久数据库连接: {self.db_file}")
            except sqlite3.Error as e:
                logging.error(f"创建数据库连接失败: {e}")
                raise
        else:
            # 健康检查：验证连接是否仍然有效
            try:
                self._connection.execute("SELECT 1")
            except sqlite3.Error:
                logging.warning("检测到数据库连接失效，正在重新连接...")
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None
                return self._get_connection()  # 递归重连
                
        return self._connection

    def _initialize_db(self):
        """
        初始化 SQLite 数据库和表。
        如果表不存在，则创建 'message_counts' 表。
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS message_counts (
                        session_id TEXT PRIMARY KEY,
                        count INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.commit()
                logging.debug(f"SQLite 数据库初始化完成，文件路径: {self.db_file}")
            except sqlite3.Error as e:
                logging.error(f"初始化 SQLite 数据库失败: {e}")
                raise

    def reset_counter(self, session_id: str):
        """
        重置指定会话 ID 的消息计数器。
        
        Args:
            session_id (str): 会话 ID
        """
        if not session_id:
            logging.warning("尝试重置空 session_id 的计数器，已忽略")
            return
            
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO message_counts (session_id, count) VALUES (?, ?)",
                    (session_id, 0),
                )
                conn.commit()
                logging.debug(f"会话 {session_id} 的计数器已重置为 0。")
            except sqlite3.Error as e:
                logging.error(f"重置会话 {session_id} 计数器时发生数据库错误: {e}")
                conn.rollback()
                raise

    def increment_counter(self, session_id: str):
        """
        为指定会话 ID 的消息计数器加 1。

        Args:
            session_id (str): 会话 ID。
        """
        if not session_id:
            logging.warning("尝试增加空 session_id 的计数器，已忽略")
            return
            
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO message_counts (session_id, count) VALUES (?, 0)",
                    (session_id,),
                )  # 如果不存在则插入，初始值为0
                cursor.execute(
                    "UPDATE message_counts SET count = count + 1 WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
                logging.debug(f"会话 {session_id} 的计数器已加 1。")
            except sqlite3.Error as e:
                logging.error(f"增加会话 {session_id} 计数器时发生数据库错误: {e}")
                conn.rollback()
                raise

    def get_counter(self, session_id: str) -> int:
        """
        获取指定会话 ID 的消息计数器值。

        Args:
            session_id (str): 会话 ID。

        Returns:
            int: 会话 ID 对应的消息计数器值。如果会话 ID 不存在，则返回 0。
        """
        if not session_id:
            logging.warning("尝试获取空 session_id 的计数器，返回 0")
            return 0
            
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT count FROM message_counts WHERE session_id = ?", (session_id,)
                )
                result = cursor.fetchone()
                if result:
                    return result[0]
                else:
                    return 0  # 会话 ID 不存在，返回 0
            except sqlite3.Error as e:
                logging.error(f"获取会话 {session_id} 计数器时发生数据库错误: {e}")
                return 0  # 发生错误时返回 0

    def adjust_counter_if_necessary(self, session_id: str, context_history: list) -> bool:
        """
        检查上下文历史对话轮次长度是否小于消息计数器，如果小于则调整计数器。

        Args:
            session_id (str): 会话 ID。
            context_history (list): 大模型的上下文历史对话列表。
                                    假设 context_history 是一个消息列表，
                                    每条消息代表用户或 AI 的一次发言。
                                    轮次长度可以简单地理解为消息列表的长度。
                                    
        Returns:
            bool: True 表示计数器正常或已调整，False 表示调整失败
        """
        if not session_id:
            logging.warning("尝试调整空 session_id 的计数器，已忽略")
            return False
            
        current_counter = self.get_counter(session_id)
        history_length = len(context_history)

        if history_length < current_counter:
            logging.warning(
                f"意外情况: 会话 {session_id} 的上下文历史长度 ({history_length}) 小于消息计数器 ({current_counter})，可能存在数据不一致。"
            )
            with self._lock:
                try:
                    conn = self._get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE message_counts SET count = ? WHERE session_id = ?",
                        (history_length, session_id),
                    )
                    conn.commit()
                    logging.warning(f"计数器已调整为上下文历史长度 ({history_length})。")
                    return False
                except sqlite3.Error as e:
                    logging.error(f"调整会话 {session_id} 计数器时发生数据库错误: {e}")
                    conn.rollback()
                    return False  # 调整失败也返回 False，表示可能需要进一步处理
        else:
            logging.debug(
                f"会话 {session_id} 的上下文历史长度 ({history_length}) 与消息计数器 ({current_counter}) 一致。"
            )
            return True

    def close(self):
        """
        S0 优化: 关闭数据库连接，释放资源。
        这是显式清理方法，建议在不再使用时调用。
        """
        with self._lock:
            if self._connection and not self._closed:
                try:
                    self._connection.close()
                    logging.debug("数据库连接已关闭")
                except sqlite3.Error as e:
                    logging.error(f"关闭数据库连接时发生错误: {e}")
                finally:
                    self._connection = None
                    self._closed = True

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，自动清理资源"""
        self.close()
        return False

    def __del__(self):
        """
        S0 优化: 析构函数，确保资源被清理。
        注意：不应依赖此方法进行关键清理，应显式调用 close()
        """
        if not self._closed:
            try:
                self.close()
            except Exception:
                # 在析构函数中忽略异常，避免导致程序崩溃
                pass