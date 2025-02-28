from astrbot.api.provider import LLMResponse
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import PermissionType,permission_type
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.api.message_components import * 
from astrbot.core.log import LogManager
from astrbot.api.provider import ProviderRequest

from pymilvus import DataType
import time


from .memory_manager.context_manager import ConversationContextManager
from .memory_manager.vector_db.milvus import MilvusDatabase
from .memory_manager.embedding import OpenAIEmbeddingAPI

from typing import List, Dict, Optional
from .tools import parse_address

@register("Mnemosyne", "lxfight", "一个AstrBot插件，实现基于RAG技术的长期记忆功能。", "0.2.0", "https://github.com/lxfight/astrbot_plugin_mnemosyne")
class Mnemosyne(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

        # 设置日志
        self.logger = LogManager.GetLogger(log_name="Mnemosyne")

        # 定义向量数据库的基础结构和需要查询的内容
        # 这部分影响Milvus数据库结构，和query函数查询得到的内容
        self.schema = {
            "fields": [
                {"name": "memory_id", "dtype": DataType.INT64, "is_primary": True, "auto_id": True},
                {"name": "personality_id", "dtype": DataType.VARCHAR, "max_length": 256,"is_nullable":True},
                {"name": "session_id", "dtype": DataType.VARCHAR, "max_length": 72},
                {"name": "content", "dtype": DataType.VARCHAR, "max_length": 4096},
                {"name": "embedding", "dtype": DataType.FLOAT_VECTOR, "dim": self.config.embedding_dim,
                    "index_params": {
                        "index_type": "IVF_SQ8",
                        "metric_type": "L2",
                        "params": {"nlist": 256}
                    }},
                {"name": "create_time", "dtype": DataType.INT64}
            ],
            "description": f"对话机器人的长期记忆存储库: {self.config.collection_name}"
        }

        # 这会使得MilvusDatabase.query 函数查询时只返回content,create_time内容
        self.output_fields = ["content","create_time"]


        # 初始化数据库
        
        host,port = parse_address(self.config.address)
        self.memory_db = MilvusDatabase(host,port)
        # 使用上下文管理器管理连接
        with self.memory_db:
            # 创建集合
            self.memory_db.create_collection(self.config.collection_name, self.schema)

        # 初始化对话管理器
        self.context_manager = ConversationContextManager(
            max_turns=self.config.num_pairs,
            max_history_length=self.config.max_history_memory
        )

        # 初始化embedding API设置
        self.ebd = OpenAIEmbeddingAPI(
            model = self.config.embedding_model,
            api_key = self.config.embedding_key,
            base_url = self.config.embedding_url
        )

    
    @filter.on_llm_request()
    async def query_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        检索相关的长期记忆，并嵌入提示
        """
        # 获取会话ID
        session_id =await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, session_id)
        persona_id = conversation.persona_id

        if not persona_id:
            self.logger.warning(f"当前对话没有人格ID,可能会导致长期记忆存储出现问题")

        # 记录对话历史
        memory = self.context_manager.add_message(session_id=session_id, role="user", content=req.prompt)
        if memory:
            # 触发消息总结
            await self.Summary_long_memory(persona_id,session_id,memory)

        try:
            detailed_results = []
            # 向量化
            query_ebd = self.ebd.get_embeddings(req.prompt)

            # 是否启用人格ID隔离
            if self.config.use_personality_filtering:
                filters = f"personality_id == \"{persona_id}\" and session_id == \"{session_id}\""
            else:
                filters = f"session_id == \"{session_id}\""
            
            with self.memory_db:
                # 查询长期记忆
                search_results = self.memory_db.search(
                    collection_name = self.config.collection_name,
                    query_vector = query_ebd[0],
                    top_k = self.config.top_k,
                    filters = filters
                )
                if not search_results:
                    return
                # 提取搜索结果中的 ID
                ids = [result.id for result in search_results[0]]
                
                if ids:
                    # 构造 ID 列表的过滤条件
                    id_str = ", ".join(map(str, ids))
                    query_filters = f"memory_id in [{id_str}]"

                    detailed_results = self.memory_db.query(
                        collection_name = self.config.collection_name,
                        filters = query_filters,
                        output_fields= self.output_fields
                    )
        except Exception as e:
            self.logger.error(f"长期记忆查询发生错误：\n{e}")
            return 
        
        if detailed_results:
            long_memory = "这里是一些长期记忆中的内容，或许会对你回答有所帮助：\n"
            for result in detailed_results:
                long_memory += f"记忆内容：{result['content']}, 时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result['create_time']))}\n"

            self.logger.info(f'得到的长期记忆：\n{long_memory}')

            req.system_prompt += long_memory
        else:
            self.logger.info("未找到相应的长期记忆，不补充")

    
    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        """
        在LLM调用完成后,添加上下文记录
        """
        session_id =await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, session_id)
        persona_id = conversation.persona_id


        if not persona_id:
            self.logger.warning(f"当前对话没有人格ID,可能会导致长期记忆存储出现问题")
        # 添加上下文
        memory = self.context_manager.add_message(session_id=session_id, role="assistant", content=resp.completion_text)

        if memory:
            # 触发消息总结
            await self.Summary_long_memory(persona_id,session_id,memory)
    
    #---------------------------------------------------------------------------#
    @command_group("memory")
    def memory_group(self):
        """长期记忆管理命令"""
        pass
    

    @memory_group.command("list")
    async def list_collections(self, event: AstrMessageEvent):
        """列出所有记忆集合 /memory list"""
        try:
            with self.memory_db:
                collections = self.memory_db.list_collections()
            response = "当前记忆集合列表：\n" + "\n".join(
                [f"🔖 {col}" for col in collections]
            )
            yield event.plain_result(response)
        except Exception as e:
            self.logger.error(f"获取集合列表失败: {str(e)}")
            yield event.plain_result(f"⚠️ 获取集合列表失败{str(e)}")
    

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("drop_collection")
    async def delete_collection(
        self,
        event: AstrMessageEvent,
        collection_name: str,
        confirm: str = None
    ):
        """
        删除向量数据库集合（需要管理员权限）
        用法：/memory drop_collection <集合名称> --confirm
        示例：/memory drop_collection test_memories --confirm
        """
        try:
            if not confirm:
                yield event.plain_result(
                    f"确认要永久删除集合 {collection_name} 吗？操作不可逆！\n"
                    f"请再次执行命令并添加 --confirm 参数"
                )
                return
            if confirm == "--confirm":
                with self.memory_db:
                    self.memory_db.drop_collection(collection_name)
                yield event.plain_result(f"✅ 已成功删除集合 {collection_name}")
                self.logger.warning(f"管理员删除了集合: {collection_name}")
            else:
                yield event.plain_result(f"请输入 --confirm 参数")

        except Exception as e:
            self.logger.error(f"删除集合失败: {str(e)}")
            yield event.plain_result(f"⚠️ 删除失败: {str(e)}")

    @memory_group.command("list_records")
    async def list_records(
        self,
        event: AstrMessageEvent,
        collection_name: str = None,
        limit: int = 10
    ):
        """
        查询指定集合的记忆记录
        用法：/memory list_records [集合名称] [数量]
        示例：/memory list_records defult 5
        """
        try:
            # 默认使用配置中的集合
            if not collection_name:
                collection_name = self.config["collection_name"]
            with self.memory_db:
                records = self.memory_db.get_latest_memory(collection_name, limit)
            
            if not records:
                yield event.plain_result("该集合暂无记忆记录")
                return
                
            response = [f"📝 集合 {collection_name} 的最新 {limit} 条记忆："]
            for i, record in enumerate(records, 1):
                time_str = record["create_time"].strftime("%Y-%m-%d %H:%M")
                response.append(
                    f"{i}. [{time_str}] {record['content']}..."
                    f"\n   SessionID: {record['session_id']}"
                )
                
            yield event.plain_result("\n\n".join(response))
            
        except Exception as e:
            self.logger.error(f"查询记录失败: {str(e)}")
            yield event.plain_result(f"⚠️ 查询记忆记录失败:{str(e)}")




    # --------------------------------------------------------------------------------#
    async def Summary_long_memory(self,persona_id, session_id, memory):
        """
        总结对话历史形成长期记忆,并插入数据库
        """
        try:
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=self.config.long_memory_prompt,
                contexts=[{"role":"user","content":f"{memory}"}]
            )

            self.logger.debug(f"llm_respone:{llm_response}")
            # 检查并提取 completion_text
            if hasattr(llm_response, "completion_text"):
                completion_text = llm_response.completion_text
            elif isinstance(llm_response, dict) and "completion_text" in llm_response:
                completion_text = llm_response["completion_text"]
            else:
                raise ValueError("llm_response 缺少 completion_text 字段")

            embedding = self.ebd.get_embeddings(completion_text)[0]

            if hasattr(llm_response, "role"):
                role = llm_response.role
            elif isinstance(llm_response, dict) and "role" in llm_response:
                role = llm_response["role"]
            else:
                raise ValueError("llm_response 缺少 role 字段")
            
            if role == "assistant":
                with self.memory_db:
                    data = [
                        {
                            "personality_id":persona_id,
                            "session_id":session_id,
                            "content":completion_text,
                            "embedding":embedding
                        }
                    ]
                    self.memory_db.insert(collection_name=self.config.collection_name, data=data)
                    self.logger.info(f"记录记忆：\n{completion_text}")
            else:
                self.logger.error(f"大语言模型总结长期记忆发生错误, 角色不是 assistant。模型回复内容：{completion_text}")
                
        except Exception as e:
            self.logger.error(f"形成长期记忆时发生错误：\n{e}")


    