import sqlite3
import os
import threading
from typing import Optional

from astrbot.core.log import LogManager

logging = LogManager.GetLogger(log_name="Message Counter")


class MessageCounter:
    """
    消息计数器类，使用 SQLite 存储每个会话的消息轮次计数。
    
    优化说明 (Phase 1 - P0):
    - 实现持久数据库连接，避免每次操作创建新连接
    - 添加线程锁确保线程安全
    - 实现连接健康检查和自动重连
    - 支持上下文管理器和资源清理
    """

    def __init__(self, db_file: Optional[str] = None):
        """
        初始化消息计数器，使用 SQLite 数据库存储。
        db_file 参数现在是可选的。如果为 None，则自动生成数据库文件路径。

        Args:
            db_file (str, optional): SQLite 数据库文件路径。
                                     如果为 None，则自动生成路径。
        """
        if db_file is None:
            # 使用 pathlib 进行更安全的路径处理
            from pathlib import Path
            
            # 获取当前文件所在目录，然后向上3层
            current_file_path = Path(__file__).resolve()
            base_dir = current_file_path.parents[3]  # 直接使用 parents 索引向上遍历

            # 构建 mnemosyne_data 文件夹路径
            data_dir = base_dir / "mnemosyne_data"

            # 确保 mnemosyne_data 文件夹存在，如果不存在则创建
            os.makedirs(
                data_dir, exist_ok=True
            )  # exist_ok=True 表示如果目录已存在，不会抛出异常

            self.db_file = os.path.join(data_dir, "message_counters.db")
        else:
            self.db_file = db_file  # 如果用户显式提供了 db_file，则使用用户提供的路径

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