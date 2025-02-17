from astrbot.api.provider import LLMResponse
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.api.message_components import *
from astrbot.core.log import LogManager
from astrbot.api.provider import ProviderRequest

from openai import OpenAI

from .milvus_processor.milvus_memory import MilvusMemory
from .history_manager.llm_his_conv_manager import MultiConversationManager

@register("Mnemosyne", "lxfight", "一个AstrBot插件，实现基于RAG技术的长期记忆功能。", "0.1.0", "https://github.com/lxfight/astrbot_plugin_mnemosyne")
class Mnemosyne(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

        # 设置日志
        self.logger = LogManager.GetLogger(log_name="Mnemosyne")
        self.msm = MultiConversationManager()
        self.base_memory = MilvusMemory(
            address=self.config.address, 
            embedding_dim=self.config.embedding_dim,
        )
    @filter.on_llm_request()
    async def search_memory_and_concat(self, event: AstrMessageEvent, req: ProviderRequest):
        """
            检索相关的长期记忆信息
        """
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        self.msm.create_conversation(curr_cid)
        self.msm.add_message_active("user",req.prompt)

        # self.logger.debug(f"req：{req}")
        memory = None
        try:
            memory = MilvusMemory(
                address=self.config.address, 
                embedding_dim=self.config.embedding_dim, 
                collection_name=req.conversation.persona_id
            )
        except Exception as err:
            self.logger.error(f"milvus数据库连接失败{err}")
            return
        
        try:
            query_embedding = self._get_text_embedding(req.prompt)
            if not query_embedding:
                self.logger.error("向量化失败，无法进行搜索。")
                return
            # 调用 Milvus 的搜索接口，返回 top_K 个结果
            top_k = getattr(self.config, "top_k", None)
            if not isinstance(top_k, int) or top_k <= 0:
                top_k = 5
            results = memory.search_memory(query_embedding,top_k,1)
            self.logger.debug(f"RAG检索的结果：{results}")

            # 将返回结果中的 metadata 字段拼接为一个字符串
            concatenated = "\n".join(
                f"{hit.entity.get('metadata') or ''} 。发生时间：{hit.entity.get('timestamp') or ''}"
                for hits in results
                for hit in hits
                if hit.entity.get("metadata")
            )


            req.system_prompt += "以下这部分是长期记忆内容，或许会对你有帮助：" + concatenated
        except Exception as err:
            self.logger.error(f"检索长期记忆时出错：{err}")
        finally:
            if memory:
                memory.disconnect()


    @filter.on_llm_response()
    async def process_long_memory(self, event: AstrMessageEvent, resp: LLMResponse):
        """
            在LLM调用完成后，判断是否需要形成长期记忆
        """
        
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
        conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, curr_cid)
        self.msm.create_conversation(curr_cid)
        self.msm.add_message_active("assistant",resp.completion_text)

        context = self.msm.get_history()

        # 如果对话历史长度没有超过配置，则不进行总结
        if len(context) < self.config.max_history_memory:
            self.logger.info(f"对话历史长度：{len(context)}")
            return
        
        # 处理历史消息
        old_context,new_context = self.msm.extract_oldest_conversation_pairs(
            conversation_id=self.msm.active_conversation,
            num_pairs=self.config.num_pairs
        )
        
        # 获取对话总结
        llm_response = await self.context.get_using_provider().text_chat(
            prompt=self.config.long_memory_prompt,
            contexts=old_context,
        )

        if llm_response.role == "assistant":
            long_memory_f = await self._insert_memory(conversation.persona_id,llm_response.completion_text)
            if long_memory_f:
                self.logger.info(f"形成长期记忆：{llm_response.completion_text}")
            else:
                self.logger.error(f"长期记忆插入失败")

            

    async def _insert_memory(self, persona_id, long_memory):
        """
            向milvus数据库插入数据,根据使用的人格进行区分
        """
        memory = None
        try:
            memory = MilvusMemory(
                address=self.config.address, 
                embedding_dim=self.config.embedding_dim, 
                collection_name=persona_id
            )

            embedding = self._get_text_embedding(long_memory)
            if embedding:
                insert_result = memory.add_memory(embedding, long_memory)
                return True
            return False
        except Exception as e:
            self.logger.debug(f"milvus插入数据出错：{e}")
            return False
        finally:
            if memory:
                memory.disconnect()

    def _get_text_embedding(self, text:str):
        """
            向量化
        """
        try:
            client = OpenAI(
                api_key=self.config.embedding_key,
                base_url=self.config.embedding_url
            )

            completion = client.embeddings.create(
                model=self.config.embedding_model,
                input=text
            )

            embedding = completion.data[0].embedding
            return embedding
        except Exception as e:
            self.logger.error(f"向量模型服务出错，向量化失败{e}")
            return None
        finally:
            client.close()
        
    @command_group("memory")
    def memory(self):
        pass
    
    @memory.command("list")
    async def list(self, event: AstrMessageEvent):
        yield event.plain_result(f"当前milvus数据库有如下集合：{self.base_memory.list_collections()}")

    @memory.command("delete")
    async def delete(self, event: AstrMessageEvent, collection_name = None):
        """
            delete 默认删除全部集合
            delete <集合名称>  删除指定集合
        """
        if not collection_name:
            self.base_memory.delete_all_collections()
            yield event.plain_result("当前milvus数据库中集合已完全删除")
        else:
            self.base_memory.delete_collection(collection_name)
            yield event.plain_result(f"{collection_name}集合已被删除")
