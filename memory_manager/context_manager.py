import copy
import threading
import time
from datetime import datetime

from astrbot.api.event import AstrMessageEvent


class ConversationContextManager:
    """
    会话上下文管理器

    M18 修复: 改进并发安全性
    - 在异步环境中，如果所有操作都在同一个事件循环线程中执行，threading.RLock 是安全的
    - 保留 RLock 用于同步代码路径
    - 添加注释说明并发安全策略
    """

    def __init__(self):
        self.conversations: dict[str, dict] = {}
        # 使用 RLock 保证线程安全
        # 注意: 这个类的方法主要在 asyncio 事件循环中调用
        # RLock 可以保护同步代码路径，对于异步代码，Python 的 GIL 和单线程事件循环提供了基本保护
        # 如果未来需要真正的异步锁，应该使用 asyncio.Lock
        self._lock = threading.RLock()

    def init_conv(self, session_id: str, contexts: list[dict], event: AstrMessageEvent):
        """
        从AstrBot获取历史消息
        """
        with self._lock:
            if session_id in self.conversations:
                return
            self.conversations[session_id] = {}
            # AstrBot passes req.contexts here. Keep an isolated snapshot so
            # add_message() cannot append plugin-only entries to the live LLM
            # request through a shared mutable list reference.
            self.conversations[session_id]["history"] = copy.deepcopy(contexts)
            self.conversations[session_id]["event"] = event
            # 初始化最后一次总结的时间，这里在重启的时候会丢失，但是先不管了
            # 重启了计时器就重启，用户再一次对话再重启计时器，emmmm，之后再改了，加个TODO
            # TODO 考虑是否需要保存到数据库中，或者保存到文件
            self.conversations[session_id]["last_summary_time"] = time.time()
            return

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> str | None:
        """
        添加对话消息
        :param session_id: 会话ID
        :param role: 角色（user/assistant）
        :param content: 对话内容
        :return: 达到阈值时返回需要总结的内容字符串，否则返回 None
        """
        with self._lock:
            if session_id not in self.conversations:
                self.conversations[session_id] = {
                    "history": [],
                    "last_summary_time": time.time(),
                }

            conversation = self.conversations[session_id]
            now_epoch = int(time.time())
            item = {
                "role": role,
                "content": content,
                # 兼容旧逻辑保留可读时间，同时提供稳定的 epoch 供后续逻辑使用。
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "timestamp_epoch": now_epoch,
            }
            if isinstance(metadata, dict) and metadata:
                item["metadata"] = metadata

            conversation["history"].append(item)

    def get_summary_time(self, session_id: str) -> float:
        """
        获取最后一次总结时间
        """
        with self._lock:
            if session_id in self.conversations:
                return self.conversations[session_id]["last_summary_time"]
            else:
                return 0

    def update_summary_time(self, session_id: str):
        """
        更新最后一次总结时间
        """
        with self._lock:
            if session_id in self.conversations:
                self.conversations[session_id]["last_summary_time"] = time.time()

    def get_history(self, session_id: str) -> list[dict]:
        """
        获取对话历史记录
        :param session_id: 会话ID
        :return: 对话历史记录
        """
        with self._lock:
            if session_id in self.conversations:
                return self.conversations[session_id]["history"]
            else:
                return []

    def clear_role_messages(self, session_id: str, role: str) -> int:
        """
        删除指定会话中指定角色的临时消息。
        """
        with self._lock:
            if session_id not in self.conversations:
                return 0
            history = self.conversations[session_id].get("history", [])
            if not isinstance(history, list):
                return 0
            kept_history = [
                message
                for message in history
                if not (isinstance(message, dict) and message.get("role") == role)
            ]
            removed = len(history) - len(kept_history)
            if removed:
                self.conversations[session_id]["history"] = kept_history
            return removed

    def clear_role_messages_by_metadata(
        self,
        session_id: str,
        role: str,
        metadata_key: str,
        metadata_values: set[str],
    ) -> int:
        """删除指定角色中 metadata 字段匹配的消息。"""
        if not metadata_values:
            return 0
        with self._lock:
            if session_id not in self.conversations:
                return 0
            history = self.conversations[session_id].get("history", [])
            if not isinstance(history, list):
                return 0

            def should_remove(message: dict) -> bool:
                metadata = message.get("metadata")
                return (
                    message.get("role") == role
                    and isinstance(metadata, dict)
                    and metadata.get(metadata_key) in metadata_values
                )

            kept_history = [
                message
                for message in history
                if not (isinstance(message, dict) and should_remove(message))
            ]
            removed = len(history) - len(kept_history)
            if removed:
                self.conversations[session_id]["history"] = kept_history
            return removed

    def trim_role_messages(self, session_id: str, role: str, keep_last: int) -> int:
        """
        只保留指定会话中最近 keep_last 条指定角色消息。
        """
        with self._lock:
            if keep_last < 0:
                keep_last = 0
            if session_id not in self.conversations:
                return 0
            history = self.conversations[session_id].get("history", [])
            if not isinstance(history, list):
                return 0

            role_indices = [
                index
                for index, message in enumerate(history)
                if isinstance(message, dict) and message.get("role") == role
            ]
            remove_count = max(0, len(role_indices) - keep_last)
            if remove_count <= 0:
                return 0

            indices_to_remove = set(role_indices[:remove_count])
            self.conversations[session_id]["history"] = [
                message
                for index, message in enumerate(history)
                if index not in indices_to_remove
            ]
            return remove_count

    def get_session_context(self, session_id: str):
        """
        获取session_id对应的所有信息
        """
        with self._lock:
            if session_id in self.conversations:
                return self.conversations[session_id]
            else:
                return {}
