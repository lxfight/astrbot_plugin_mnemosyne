from typing import List, Dict, Optional
import time
from astrbot.core.log import LogManager


class ConversationContextManager:
    """
    自动管理对话历史的上下文管理器
    功能：当对话轮次达到阈值时，返回需要总结的对话内容字符串，并支持多个会话
    """

    def __init__(self, max_turns: int = 10, max_history_length: int = 20):
        """
        :param max_turns: 触发总结的对话轮次阈值
        :param max_history_length: 记录的最大历史长度
        """
        self.max_turns = max_turns
        self.max_history_length = max_history_length
        self.conversations: Dict[str, Dict] = {}
        self.logger = LogManager.GetLogger(log_name="Conversation Context Manager")

    def _reset_counter(self, session_id: str):
        """重置指定会话的计数器"""
        if session_id in self.conversations:
            self.conversations[session_id]["turn_count"] = 0
            self.conversations[session_id]["last_summary_time"] = time.time()

    def add_message(self, session_id: str, role: str, content: str) -> Optional[str]:
        """
        添加对话消息
        :param session_id: 会话ID
        :param role: 角色（user/assistant）
        :param content: 对话内容
        :return: 达到阈值时返回需要总结的内容字符串，否则返回 None
        """
        if session_id not in self.conversations:
            self.conversations[session_id] = {
                "history": [],
                "turn_count": 0,
                "last_summary_time": time.time(),
            }

        conversation = self.conversations[session_id]
        conversation["history"].append(
            {
                "role": role,
                "content": content,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        conversation["turn_count"] += 1
        self.logger.debug(f"对话计数器：{conversation['turn_count']}条")
        # 保持历史记录在最大长度内
        if len(conversation["history"]) > self.max_history_length:
            conversation["history"] = conversation["history"][
                -self.max_history_length :
            ]

        if conversation["turn_count"] >= self.max_turns:
            return self._generate_summary_content(session_id)
        return None

    def _generate_summary_content(self, session_id: str) -> str:
        """生成待总结的对话内容字符串"""
        conversation = self.conversations[session_id]
        summary = "\n".join(
            [
                f"[{msg['timestamp']}] {msg['role']}: {msg['content']}"
                for msg in conversation["history"][-self.max_turns :]
            ]
        )
        self._reset_counter(session_id)
        return summary

    def get_full_history(self, session_id: str) -> str:
        """获取指定会话的完整对话历史（用于调试）"""
        if session_id in self.conversations:
            conversation = self.conversations[session_id]
            return "\n".join(
                [
                    f"[{msg['timestamp']}] {msg['role']}: {msg['content']}"
                    for msg in conversation["history"]
                ]
            )
        else:
            return "会话ID不存在"

    def summarize_memory(self, session_id: str, role: str, contents: List) -> str:
        """
        通过历史上下文，格式化处理为短期上下文
        :param session_id: 会话ID
        :param role: 角色（user/assistant）
        :param contents: 待处理的历史上下文
        :return: 返回短期记忆
        """
        # 检查 会话 是否存在于 conversations 内
        if session_id not in self.conversations:
            self.conversations[session_id] = {
                "history": [],
                "turn_count": 0,
                "last_summary_time": time.time(),
            }

        conversation = self.conversations[session_id]
        for content in contents:
            conversation["history"].append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            conversation["turn_count"] += 1

        # 返回 格式化 后的 短期上下文
        return self._generate_summary_content(session_id)
