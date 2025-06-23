from typing import List, Dict, Optional
import time
from astrbot.api.event import AstrMessageEvent


class ConversationContextManager:
    """
    会话上下文管理器
    """

    def __init__(self):
        self.conversations: Dict[str, Dict] = {}

    def init_conv(self, session_id: str, contexts: list[Dict], event: AstrMessageEvent):
        """
        从AstrBot获取历史消息
        """
        if session_id in self.conversations:
            return
        self.conversations[session_id] = {}
        self.conversations[session_id]["history"] = contexts
        self.conversations[session_id]["event"] = event
        # 初始化最后一次总结的时间，这里在重启的时候会丢失，但是先不管了
        # 重启了计时器就重启，用户再一次对话再重启计时器，emmmm，之后再改了，加个TODO
        # TODO 考虑是否需要保存到数据库中，或者保存到文件
        self.conversations[session_id]["last_summary_time"] = time.time()
        return

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
                "last_summary_time": time.time(),
            }

        conversation = self.conversations[session_id]
        conversation["history"].append(
            {
                "role": role,
                "content": content,
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),  # 这个是不会被加入到总结的内容中的，应该
            }
        )

    def get_summary_time(self, session_id: str) -> float:
        """
        获取最后一次总结时间
        """
        if session_id in self.conversations:
            return self.conversations[session_id]["last_summary_time"]
        else:
            return 0

    def update_summary_time(self, session_id: str):
        """
        更新最后一次总结时间
        """
        if session_id in self.conversations:
            self.conversations[session_id]["last_summary_time"] = time.time()

    def get_history(self, session_id: str) -> List[Dict]:
        """
        获取对话历史记录
        :param session_id: 会话ID
        :return: 对话历史记录
        """
        if session_id in self.conversations:
            return self.conversations[session_id]["history"]
        else:
            return []

    def get_session_context(self, session_id: str):
        """
        获取session_id对应的所有信息
        """
        if session_id in self.conversations:
            return self.conversations[session_id]
        else:
            return {}
