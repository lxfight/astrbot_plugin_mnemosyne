class MultiConversationManager:
    def __init__(self):
        """
        初始化一个多会话管理器，能够管理多个不同的对话历史记录。
        """
        self.conversations = {}  # 用于存储不同会话历史的字典，key: 会话ID, value: 消息列表
        self.active_conversation = None

    def create_conversation(self, conversation_id: str, system_prompt: str = None):
        """
        创建一个新的对话历史记录。如果对话已经存在，则切换到那个对话。
        
        :param conversation_id: 用于标识该对话的唯一ID
        :param system_prompt: 可选的系统提示消息，将作为该对话的第一条消息
        """
        if conversation_id in self.conversations:
            # 对话已存在，直接切换
            self.active_conversation = conversation_id
            return

        self.conversations[conversation_id] = []
        if system_prompt:
            self.add_message(conversation_id, "system", system_prompt)
        self.active_conversation = conversation_id

    def switch_conversation(self, conversation_id: str):
        """
        切换到指定的对话历史记录。
        
        :param conversation_id: 目标对话ID
        :raises ValueError: 如果指定的对话不存在
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"对话 '{conversation_id}' 不存在。")
        self.active_conversation = conversation_id

    def add_message(self, conversation_id: str, role: str, content: str):
        """
        向指定的对话中添加一条消息。
        
        :param conversation_id: 目标对话ID
        :param role: 消息角色，必须为 "system", "user" 或 "assistant"
        :param content: 消息内容文本
        :raises ValueError: 如果 role 不合法或指定的对话不存在
        """
        if role not in {"system", "user", "assistant"}:
            raise ValueError("角色必须为 'system', 'user' 或 'assistant'")
        if conversation_id not in self.conversations:
            raise ValueError(f"对话 '{conversation_id}' 不存在。")
        self.conversations[conversation_id].append({"role": role, "content": content})

    def add_message_active(self, role: str, content: str):
        """
        向当前活跃的对话中添加一条消息。
        
        :param role: 消息角色
        :param content: 消息内容文本
        :raises ValueError: 如果没有活跃对话
        """
        if self.active_conversation is None:
            raise ValueError("没有活跃的对话，请先创建或切换到一个对话。")
        self.add_message(self.active_conversation, role, content)

    def get_history(self, conversation_id: str = None) -> list:
        """
        获取指定对话的历史记录。
        
        :param conversation_id: 对话ID。如果为 None，则返回当前活跃对话的历史记录。
        :return: 消息列表，每条消息均为字典格式 {"role": role, "content": content}
        :raises ValueError: 如果指定的对话不存在或者没有活跃对话
        """
        if conversation_id is None:
            if self.active_conversation is None:
                raise ValueError("没有活跃的对话。")
            conversation_id = self.active_conversation

        if conversation_id not in self.conversations:
            raise ValueError(f"对话 '{conversation_id}' 不存在。")
        return self.conversations[conversation_id]

    def delete_conversation(self, conversation_id: str):
        """
        删除指定的对话历史记录。
        
        :param conversation_id: 对话ID
        """
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            if self.active_conversation == conversation_id:
                self.active_conversation = None

    def list_conversations(self) -> list:
        """
        列出所有已存在的对话ID。
        
        :return: 对话ID列表
        """
        return list(self.conversations.keys())
    
    def extract_oldest_conversation_pairs(self, conversation_id: str = None, num_pairs: int = 5):
        """
        从指定对话历史中提取最旧的 num_pairs 对（user 与 assistant 消息构成的一问一答对），
        并返回两个列表：
          - extracted：提取出的对话记录（仅包含 user 和 assistant 消息）
          - new_context：更新后的对话历史，已移除提取出的对话对，但保留所有 system 消息
          
        同时更新该对话的历史记录。
        
        :param conversation_id: 对话ID。如果为 None，则使用当前活跃对话。
        :param num_pairs: 需要提取的问答对数量，默认 5 对。
        :return: (extracted, new_context)
        :raises ValueError: 如果没有活跃对话或指定的对话不存在
        """
        if conversation_id is None:
            if self.active_conversation is None:
                raise ValueError("没有活跃的对话，无法提取对话对。")
            conversation_id = self.active_conversation

        if conversation_id not in self.conversations:
            raise ValueError(f"对话 '{conversation_id}' 不存在。")

        context = self.conversations[conversation_id]
        extracted = []
        new_context = []
        pairs_extracted = 0
        i = 0
        n = len(context)

        while i < n:
            # 如果已提取足够的对话对，剩余消息全部保留
            if pairs_extracted >= num_pairs:
                new_context.extend(context[i:])
                break

            current_msg = context[i]
            # 如果当前消息不是 user 消息（例如 system 或 assistant），直接保留
            if current_msg.get("role") != "user":
                new_context.append(current_msg)
                i += 1
            else:
                # 当前为 user 消息，检查下一条消息是否为 assistant，构成完整问答对
                if i + 1 < n and context[i+1].get("role") == "assistant":
                    extracted.append(current_msg)
                    extracted.append(context[i+1])
                    pairs_extracted += 1
                    i += 2  # 跳过这一对消息
                else:
                    # 如果没有对应的 assistant 消息，则保留当前消息
                    new_context.append(current_msg)
                    i += 1

        # 更新该对话的历史记录
        self.conversations[conversation_id] = new_context
        return extracted, new_context