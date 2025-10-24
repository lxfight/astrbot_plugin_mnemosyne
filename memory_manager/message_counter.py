import sqlite3
import os

from astrbot.core.log import LogManager

logging = LogManager.GetLogger(log_name="Message Counter")


class MessageCounter:
    """
    消息计数器类，使用 SQLite 存储每个会话的消息轮次计数。
    """

    def __init__(self, db_file=None):
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

        self._initialize_db()

    def _initialize_db(self):
        """
        初始化 SQLite 数据库和表。
        如果表不存在，则创建 'message_counts' 表。
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_counts (
                    session_id TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.commit()
            logging.debug(f"SQLite 数据库初始化完成，文件路径: {self.db_file}")
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            logging.error(f"初始化 SQLite 数据库失败: {e}")
            if conn:
                conn.rollback()  # 回滚事务
        finally:
            if conn:
                conn.close()

    def reset_counter(self, session_id):
        """
        重置指定会话 ID 的消息计数器。
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO message_counts (session_id, count) VALUES (?, ?)",
                (session_id, 0),
            )
            conn.commit()
            logging.debug(f"会话 {session_id} 的计数器已重置为 0。")
        except sqlite3.Error as e:
            logging.error(f"重置会话 {session_id} 计数器时发生数据库错误: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def increment_counter(self, session_id):
        """
        为指定会话 ID 的消息计数器加 1。

        Args:
            session_id (str): 会话 ID。
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
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
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def get_counter(self, session_id):
        """
        获取指定会话 ID 的消息计数器值。

        Args:
            session_id (str): 会话 ID。

        Returns:
            int: 会话 ID 对应的消息计数器值。如果会话 ID 不存在，则返回 0。
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
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
            return 0  # 发生错误时返回 0，或者可以考虑抛出异常，根据具体需求决定
        finally:
            if conn:
                conn.close()

    def adjust_counter_if_necessary(self, session_id, context_history):
        """
        检查上下文历史对话轮次长度是否小于消息计数器，如果小于则调整计数器。

        Args:
            session_id (str): 会话 ID。
            context_history (list): 大模型的上下文历史对话列表。
                                    假设 context_history 是一个消息列表，
                                    每条消息代表用户或 AI 的一次发言。
                                    轮次长度可以简单地理解为消息列表的长度。
        """
        current_counter = self.get_counter(session_id)
        history_length = len(context_history)

        if history_length < current_counter:
            logging.warning(
                f"意外情况: 会话 {session_id} 的上下文历史长度 ({history_length}) 小于消息计数器 ({current_counter})，可能存在数据不一致。"
            )
            conn = None
            try:
                conn = sqlite3.connect(self.db_file)
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
                if conn:
                    conn.rollback()
                return False  # 调整失败也返回 False，表示可能需要进一步处理
            finally:
                if conn:
                    conn.close()
        else:
            logging.debug(
                f"会话 {session_id} 的上下文历史长度 ({history_length}) 与消息计数器 ({current_counter}) 一致。"
            )
            return True
