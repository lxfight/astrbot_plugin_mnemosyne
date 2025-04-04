from astrbot.api.provider import LLMResponse
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.event.filter import PermissionType,permission_type
from astrbot.api.star import Context, Star, register
from astrbot.api.all import *
from astrbot.api.message_components import * 
from astrbot.core.log import LogManager
from astrbot.api.provider import ProviderRequest,Personality

import re
import time
from datetime import datetime

from .memory_manager.context_manager import ConversationContextManager
# from .memory_manager.vector_db.milvus import MilvusDatabase
from .memory_manager.vector_db.milvus_manager import MilvusManager
from .memory_manager.embedding import OpenAIEmbeddingAPI

from typing import List, Dict, Optional
from .tools import parse_address

from pymilvus import (
    connections, utility, CollectionSchema, FieldSchema, DataType,
    Collection, AnnSearchRequest, RRFRanker, WeightedRanker
)
from pymilvus.exceptions import MilvusException, CollectionNotExistException, IndexNotExistException
import asyncio

# --- Constants ---
DEFAULT_COLLECTION_NAME = "default"
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_HISTORY = 20
DEFAULT_TOP_K = 5
DEFAULT_MILVUS_TIMEOUT = 5 # seconds
DEFAULT_PERSONA_ON_NONE = "UNKNOWN_PERSONA"
VECTOR_FIELD_NAME = "embedding"
PRIMARY_FIELD_NAME = "memory_id"
DEFAULT_OUTPUT_FIELDS = ["content", "create_time", PRIMARY_FIELD_NAME]


@register("Mnemosyne", "lxfight", "一个AstrBot插件，实现基于RAG技术的长期记忆功能。", "0.3.1", "https://github.com/lxfight/astrbot_plugin_mnemosyne")
class Mnemosyne(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.context = context
        # 设置日志
        self.logger = LogManager.GetLogger(log_name="Mnemosyne")


        # --- 初始化核心组件 ---
        self.collection_schema: Optional[CollectionSchema] = None
        self.index_params: dict = {}
        self.search_params: dict = {}
        self.output_fields_for_query: List[str] = []
        self.collection_name: str = DEFAULT_COLLECTION_NAME
        self.primary_field_name = PRIMARY_FIELD_NAME
        self.vector_field_name = VECTOR_FIELD_NAME
        self.milvus_manager: Optional[MilvusManager] = None
        self.context_manager: Optional[ConversationContextManager] = None
        self.ebd: Optional[OpenAIEmbeddingAPI] = None

        try:
            # 1. 配置架构和参数
            self._initialize_config_and_schema()

            # 2. 初始化并连接到Milvus
            self._initialize_milvus()

            # 3. 初始化其他组件（上下文管理器，嵌入API）
            self._initialize_components()

            self.logger.info("Mnemosyne插件初始化成功。")

        except Exception as e:
            self.logger.error(f"Mnemosyne插件初始化失败: {e}", exc_info=True)
            # 根据严重程度，可能需要禁用该插件
            # 目前，组件可能保持None，稍后需要进行检查。
            # raise RuntimeError(f"Mnemosyne插件初始化失败: {e}") from e

    @filter.on_llm_request()
    async def query_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        检索相关的长期记忆，并嵌入提示
        """

        # 根据配置，删除上下文中超过配置数量的长期记忆
        i = 0
        for record in reversed(req.contexts):
            if record.get("role") == "user":
                i += 1
                # 如果配置为负数，不做任何处理
                if self.config.contexts_memory_len < 0:
                    break
                # 超过配置数量的长期记忆，进行清除
                if(i > self.config.contexts_memory_len):

                    raw_content = record.get("content", "")
                    clean_content = re.sub(r'<Mnemosyne>.*?</Mnemosyne>', '', raw_content, flags=re.DOTALL)

                    record['content'] = clean_content  # 这会直接修改原字典对象

                    self.logger.info(f"修改后的用户输入内容: {clean_content}")
                    break

        if not self.milvus_manager:
            self.logger.error("MilvusManager 未初始化，无法查询长期记忆。")
            return
        if not self.ebd:
            self.logger.error("Embedding API 未初始化，无法查询长期记忆。")
            return

        try:
            # 获取会话和人格信息
            session_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
            conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, session_id)
            persona_id = conversation.persona_id
            # 获取默认人格 if needed
            if not persona_id or persona_id == "[%None]":
                default_persona = self.context.provider_manager.selected_default_persona
                persona_id = default_persona["name"] if default_persona else None # 如果没有default，则使用None

            if not persona_id:
                self.logger.warning(f"当前会话 (ID: {session_id}) 没有有效的人格ID，将不按人格过滤记忆。")


            # 记录用户消息到短期上下文
            memory_summary = self.context_manager.add_message(session_id=session_id, role="user", content=req.prompt)
            
            if memory_summary:
                # 触发消息总结 (异步，不阻塞查询)
                # 确保persona_id正确传递（可能是None）
                asyncio.create_task(self.Summary_long_memory(persona_id, session_id, memory_summary))


            # --- RAG 搜索 ---
            detailed_results = []
            try:
                # 1. 向量化查询
                query_embeddings = self.ebd.get_embeddings(req.prompt)
                if not query_embeddings:
                    self.logger.error("无法获取查询的 embedding。")
                    return
                query_vector = query_embeddings[0]

                # 2. 构建搜索筛选表达式
                # 会话的基本过滤器
                filters = [f"session_id == \"{session_id}\""]
                # 如果人格可用且配置
                if self.config.get("use_personality_filtering", False) and persona_id:
                    filters.append(f"personality_id == \"{persona_id}\"")
                # 拼接过滤器
                search_expression = " and ".join(filters)


                # 3. 执行搜索
                collection_name = self.config.get('collection_name', DEFAULT_COLLECTION_NAME)
                top_k = self.config.get("top_k", DEFAULT_TOP_K)
                timeout_seconds = DEFAULT_MILVUS_TIMEOUT # 默认5秒超时

                self.logger.info(f"搜索集合 '{collection_name}' (TopK: {top_k}, Filter: '{search_expression}')")

                try:
                    # 使用asyncio.wait_for添加超时控制
                    search_results = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.milvus_manager.search(
                                collection_name=collection_name,
                                query_vectors=[query_vector], # 传递一个向量列表
                                vector_field=self.vector_field_name,
                                search_params=self.search_params, # 使用预定义的搜索参数
                                limit=top_k,
                                expression=search_expression,
                                # 指定搜索所需的输出字段，通常ID和距离是默认值
                                # 如果你需要“content”直接从搜索，添加到这里，但查询下面通常是首选
                                # output_fields=[self.primary_field_name], # 只从搜索中获取id
                                output_fields=self.output_fields_for_query, # 如果愿意，也可以直接获取详细信息
                                # consistency_level=self.config.get("consistency_level", "Bounded") # 可选
                            )
                        ),
                        timeout=timeout_seconds
                    )
                except asyncio.TimeoutError:
                    self.logger.error(f"Milvus查询超时（{timeout_seconds}秒），已取消操作")
                    return
                except Exception as e:
                    self.logger.error(f"Milvus查询执行失败: {e}", exc_info=True)
                    return
                


                # 4. 处理搜索结果
                if not search_results or not search_results[0]: # search_results是列表[SearchResult]
                    self.logger.info("向量搜索未找到相关记忆。")
                    return
                # self.logger.debug(f"搜索结果: {search_results}")

                # 如果搜索output_fields包含完整的详细信息：
                if self.output_fields_for_query:
                    hits = search_results[0] 
                    detailed_results = [hit.entity.to_dict() for hit in hits if hasattr(hit, 'entity')]

            except MilvusException as me:
                self.logger.error(f"Milvus 操作（搜索/查询）失败: {me}", exc_info=True)
                return # 在Milvus错误时停止处理
            except Exception as e:
                self.logger.error(f"处理长期记忆查询时发生错误: {e}", exc_info=True)
                return # 在一般错误时停止处理

            # self.logger.debug(f"详细结果: {detailed_results}")
            # 5. 格式化结果并注入到提示符中
            if detailed_results:
                long_memory = "<Mnemosyne>这里是一些可能相关的长期记忆片段：\n"
                # 排序结果。。。。。Milvus搜索按距离返回。查询顺序难以预测。
                # 如果使用查询，如果id被映射，可能会按原始搜索距离排序？
                # 为简单起见，使用返回的顺序。
                for result in detailed_results:
                    content = result['entity'].get('content', '无内容')
                    ts = result['entity'].get('create_time')
                    time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M') if ts else '未知时间'
                    long_memory += f"- [{time_str}] {content}\n"
                    
                long_memory += "</Mnemosyne>"

                self.logger.info(f'补充的长期记忆:\n{long_memory}')
                # 根据策略追加到系统提示符或用户提示符
                req.prompt = (req.prompt or "") + "\n" + long_memory
            else:
                self.logger.info("未找到或获取到相关的长期记忆，不补充。")

        except Exception as e:
            # 捕捉外部逻辑中的错误（获取会话ID等）
            self.logger.error(f"处理 LLM 请求前的记忆查询失败: {e}", exc_info=True)

    
    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        """
        在LLM调用完成后,添加上下文记录
        """
        if not self.milvus_manager:
            self.logger.error("MilvusManager 未初始化，无法记录长期记忆。")
            return

        try:
            session_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)
            conversation = await self.context.conversation_manager.get_conversation(event.unified_msg_origin, session_id)
            persona_id = conversation.persona_id
            # 如果需要，获取默认角色
            if not persona_id or persona_id == "[%None]":
                default_persona = self.context.provider_manager.selected_default_persona
                persona_id = default_persona["name"] if default_persona else None

            if not persona_id:
                self.logger.warning(f"当前对话 (ID: {session_id}) 没有有效的人格ID，将不按人格存储记忆。")

            # 添加 LLM 响应到短期上下文
            memory_summary = self.context_manager.add_message(session_id=session_id, role="assistant", content=resp.completion_text)

            if memory_summary:
                # 触发消息总结 (异步)
                asyncio.create_task(self.Summary_long_memory(persona_id, session_id, memory_summary))

        except Exception as e:
            self.logger.error(f"处理 LLM 响应后的记忆记录失败: {e}", exc_info=True)
    
    #---------------------------------------------------------------------------#
    @command_group("memory")
    def memory_group(self):
        """长期记忆管理命令"""
        pass
    

    @memory_group.command("list")
    async def list_collections_cmd(self, event: AstrMessageEvent):
        """列出所有记忆集合 /memory list"""
        if not self.milvus_manager:
            yield event.plain_result("⚠️ Milvus 服务未初始化。")
            return
        try:
            collections = self.milvus_manager.list_collections()
            if collections is None: # Check for failure
                yield event.plain_result(f"⚠️ 获取集合列表失败 (返回 None)。请检查日志。")
                return

            response = "当前 Milvus 实例中的集合列表：\n" + "\n".join(
                [f"🔖 {col}" for col in collections]
            )
            yield event.plain_result(response)
        except Exception as e:
            self.logger.error(f"获取集合列表失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"⚠️ 获取集合列表时出错: {str(e)}")

    

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("drop_collection")
    async def delete_collection_cmd(
        self,
        event: AstrMessageEvent,
        collection_name: str,
        confirm: str = None
    ):
        """
        删除向量数据库集合（需要管理员权限）
        用法：/memory drop_collection <集合名称> --confirm
        示例：/memory drop_collection mnemosyne_default --confirm
        """
        if not self.milvus_manager:
            yield event.plain_result("⚠️ Milvus 服务未初始化。")
            return

        if confirm != "--confirm":
            yield event.plain_result(
                f"⚠️ 确认操作 ⚠️\n"
                f"此操作将永久删除集合 '{collection_name}' 及其所有数据！操作不可逆！\n\n"
                f"要确认删除，请再次执行命令并添加 `--confirm` 参数:\n"
                f"`/memory drop_collection {collection_name} --confirm`"
            )
            return

        try:
            self.logger.warning(f"管理员 {event.get_sender_id()} 请求删除集合: {collection_name}")
            success = self.milvus_manager.drop_collection(collection_name)
            if success:
                yield event.plain_result(f"✅ 已成功删除集合 {collection_name}")
                self.logger.warning(f"管理员 {event.get_sender_id()} 成功删除了集合: {collection_name}")
            else:
                yield event.plain_result(f"⚠️ 删除集合 {collection_name} 失败。请检查日志。")

        except Exception as e:
            self.logger.error(f"删除集合 '{collection_name}' 失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"⚠️ 删除集合时发生严重错误: {str(e)}")
    

    @memory_group.command("list_records")
    async def list_records_cmd(
        self,
        event: AstrMessageEvent,
        collection_name: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ):
        """
        查询指定集合的记忆记录 (按时间倒序)
        用法：/memory list_records [集合名称] [数量] [偏移量]
        示例：/memory list_records default 5 0
        """
        if not self.milvus_manager:
            yield event.plain_result("⚠️ Milvus 服务未初始化。")
            return

        # 默认使用配置中的集合
        target_collection = collection_name or self.config.get("collection_name", DEFAULT_COLLECTION_NAME)

        if limit <= 0 or limit > 100:
            yield event.plain_result("⚠️ 查询数量必须在 1 到 100 之间。")
            return
        if offset < 0:
            yield event.plain_result("⚠️ 偏移量不能为负数。")
            return

        try:
            # 使用 query 获取记录。Milvus query 本身不保证排序，除非通过特殊方式（如迭代器）。
            # 最简单可靠的方法是在Python中获取和排序，或者在可行的情况下使用create_time过滤器进行查询。
            # 让我们使用limit/offset获取，然后排序。
            # 获取所有记录的查询表达式：‘memory_id > 0’或类似的安全表达式。
            records = self.milvus_manager.query(
                collection_name=target_collection,
                expression=f"{self.primary_field_name} > 0", # 获取所有有效记录
                output_fields=["content", "create_time", "session_id", self.primary_field_name], # 需要的字段
                # 注意：如果排序不是原生的，那么Milvus ' query ' limit/offset可能在排序之前应用。
                # 随着时间的推移，真正的分页可能需要更多的抓取和排序/切片。
                # 我们首先直接尝试限制/偏移。
                limit=limit,
                offset=offset,
                # consistency_level=self.config.get("consistency_level", "Bounded") # 可选
            )

            if records is None:
                yield event.plain_result(f"⚠️ 查询集合 '{target_collection}' 记录失败。")
                return
            if not records:
                yield event.plain_result(f"集合 '{target_collection}' 在偏移量 {offset} 之后没有更多记录。")
                return

            # 按create_time降序排序
            records.sort(key=lambda x: x.get('create_time', 0), reverse=True)

            response = [f"📝 集合 '{target_collection}' 的记忆记录 (第 {offset+1} 到 {offset+len(records)} 条):"]
            for i, record in enumerate(records, start=offset + 1):
                ts = record.get('create_time')
                time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "未知时间"
                content_preview = record.get('content', 'N/A')[:80] + ('...' if len(record.get('content', '')) > 80 else '')
                session_id_short = record.get('session_id', 'N/A')[:12] + ('...' if len(record.get('session_id', '')) > 12 else '') # 缩短会话ID以显示
                pk = record.get(self.primary_field_name, 'N/A')
                response.append(
                    f"{i}. [时间: {time_str}]\n"
                    f"   内容: {content_preview}\n"
                    f"   会话: {session_id_short} (ID: {pk})"
                )

            yield event.plain_result("\n\n".join(response))

        except Exception as e:
            self.logger.error(f"查询集合 '{target_collection}' 记录失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"⚠️ 查询记忆记录时出错: {str(e)}")

    @permission_type(PermissionType.ADMIN)
    @memory_group.command("delete_session_memory")
    async def delete_session_memory_cmd(
        self,
        event: AstrMessageEvent,
        session_id: str,
        confirm: str = None
    ):
        """
        删除指定会话ID的所有记忆信息（需要管理员权限）
        用法：/memory delete_session_memory <会话ID> --confirm
        """
        if not self.milvus_manager:
            yield event.plain_result("⚠️ Milvus 服务未初始化。")
            return

        if not session_id:
            yield event.plain_result("⚠️ 请提供要删除记忆的会话ID。")
            return

        if confirm != "--confirm":
            yield event.plain_result(
                f"⚠️ 确认操作 ⚠️\n"
                f"此操作将永久删除会话 ID '{session_id}' 的所有记忆信息！操作不可逆！\n\n"
                f"要确认删除，请再次执行命令并添加 `--confirm` 参数:\n"
                f"`/memory delete_session_memory {session_id} --confirm`"
            )
            return

        try:
            collection_name = self.config.get("collection_name", "mnemosyne_default")
            # 构造过滤器表达式
            expr = f"session_id == \"{session_id}\"" 

            self.logger.warning(f"管理员 {event.get_sender_id()} 请求删除会话 '{session_id}' 的所有记忆 (集合: {collection_name})")

            mutation_result = self.milvus_manager.delete(
                collection_name=collection_name,
                expression=expr
            )

            if mutation_result:
                # 注意：mutation_result.delete_count在flush之前可能不准确
                yield event.plain_result(f"✅ 已成功发送删除会话 ID '{session_id}' 所有记忆的请求。更改将在后台生效 (需要 flush)。")
                self.logger.warning(f"管理员 {event.get_sender_id()} 成功发送了删除会话 '{session_id}' 记忆的请求。")
                # 如果希望立即产生效果，可选择在此处触发刷新，但可能影响性能
                self.logger.info(f"Flushing collection '{collection_name}' to apply deletion...")
                self.milvus_manager.flush([collection_name])
            else:
                yield event.plain_result(f"⚠️ 删除会话 ID '{session_id}' 的记忆失败。请检查日志。")

        except Exception as e:
            self.logger.error(f"删除会话 ID '{session_id}' 的记忆信息失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"⚠️ 删除会话记忆时发生严重错误: {str(e)}")

    @memory_group.command("get_session_id")
    async def get_session_id_cmd(self, event: AstrMessageEvent):
        """
        获取当前会话ID
        用法：/memory get_session_id
        """
        try:
            # 获取当前会话ID
            session_id = await self.context.conversation_manager.get_curr_conversation_id(event.unified_msg_origin)

            if session_id:
                yield event.plain_result(f"当前会话 ID: `{session_id}`")
            else:
                yield event.plain_result("无法获取当前会话 ID。可能尚未开始对话。")
                self.logger.warning("在 get_session_id 命令中无法获取当前会话ID。")

        except Exception as e:
            self.logger.error(f"获取当前会话 ID 失败: {str(e)}", exc_info=True)
            yield event.plain_result(f"⚠️ 获取当前会话 ID 时出错: {str(e)}")
    # --------------------------------------------------------------------------------#
    async def Summary_long_memory(self, persona_id: Optional[str], session_id: str, memory_text: str):
        """
        总结对话历史形成长期记忆,并插入数据库
        """
        if not self.milvus_manager:
            self.logger.error("MilvusManager 未初始化，无法存储总结记忆。")
            return
        if not self.ebd:
            self.logger.error("Embedding API 未初始化，无法存储总结记忆。")
            return
        if not memory_text:
            self.logger.warning("尝试总结空的记忆文本，跳过。")
            return

        try:
            # 1. 给LLM进行总结
            long_memory_prompt = self.config.get("long_memory_prompt", "请将以下对话内容总结为一段简洁的长期记忆:")
            self.logger.debug(f"请求 LLM 总结记忆，Prompt: '{long_memory_prompt[:50]}...', 内容长度: {len(memory_text)}")
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=long_memory_prompt,
                contexts=[{"role": "user", "content": memory_text}] # 通过文章进行总结
            )

            self.logger.debug(f"LLM 总结响应: {llm_response}")

            # 2. 提取摘要文本
            # 处理LLMResponse结构中的潜在变化
            completion_text = None
            role = None
            if isinstance(llm_response, LLMResponse):
                completion_text = llm_response.completion_text
                role = llm_response.role
            elif isinstance(llm_response, dict):
                completion_text = llm_response.get("completion_text")
                role = llm_response.get("role")

            if not completion_text:
                self.logger.error(f"LLM 总结响应无效或缺少 'completion_text'。响应: {llm_response}")
                return
            if role != "assistant": # 检查LLM是否正确响应
                self.logger.error(f"LLM 总结角色不是 'assistant' (而是 '{role}')。可能未成功总结。模型回复: {completion_text[:100]}...")
                # 根据此错误决定是否继续

            # 3. 获取记忆的嵌入
            embedding = self.ebd.get_embeddings(completion_text)
            if not embedding:
                self.logger.error(f"无法获取总结文本的 embedding: {completion_text[:100]}...")
                return
            embedding_vector = embedding[0]

            # 4. 准备插入数据
            collection_name = self.config.get("collection_name", "mnemosyne_default")
            current_timestamp = int(time.time()) # 在这里添加时间戳

            # 插入前处理无persona_id
            effective_persona_id = persona_id if persona_id else self.config.get("default_persona_id_on_none", DEFAULT_PERSONA_ON_NONE) # 使用默认值或占位符

            data_to_insert = [
                {
                    "personality_id": effective_persona_id,
                    "session_id": session_id,
                    "content": completion_text, # 摘要文本
                    "embedding": embedding_vector,
                    "create_time": current_timestamp # 添加时间戳
                }
            ]
            # self.logger.debug(f"准备插入数据: {data_to_insert}")

            # 5. 插入Milvus
            self.logger.info(f"准备向集合 '{collection_name}' 插入总结记忆 (Persona: {effective_persona_id}, Session: {session_id}...)")
            mutation_result = self.milvus_manager.insert(
                collection_name=collection_name,
                data=data_to_insert
                # consistency_level=self.config.get("consistency_level", "Bounded") # 可选
            )

            if mutation_result and mutation_result.insert_count > 0:
                self.logger.info(f"成功插入总结记忆。PKs: {mutation_result.primary_keys}")
                # 重要插入后立即flush
                self.logger.debug(f"Flushing collection '{collection_name}' after memory insertion.")
                self.milvus_manager.flush([collection_name])
            else:
                self.logger.error(f"插入总结记忆失败。LLM 回复: {completion_text[:100]}...")

        except Exception as e:
            self.logger.error(f"形成或存储长期记忆时发生错误: {e}", exc_info=True)

    async def terminate(self):
        """插件停止逻辑"""
        self.logger.info("Mnemosyne 插件正在停止...")
        if self.milvus_manager:
            try:
                # 从内存中释放集合
                collection_name = self.config.get('collection_name', 'mnemosyne_default')
                if self.milvus_manager.has_collection(collection_name):
                    self.logger.info(f"停止时释放集合 '{collection_name}'...")
                    self.milvus_manager.release_collection(collection_name)

                # 断开连接
                self.logger.info("断开 Milvus 连接...")
                self.milvus_manager.disconnect()
                self.logger.info("Milvus 连接已断开。")
            except Exception as e:
                self.logger.error(f"停止插件时与 Milvus 交互出错: {e}", exc_info=True)
        self.logger.info("Mnemosyne 插件已停止。")

    # --- 初始化 ---
    def _initialize_config_and_schema(self):
        """解析配置、验证和定义模式/索引参数。"""
        self.logger.debug("初始化配置和模式...")
        try:
            embedding_dim = self.config.get("embedding_dim", DEFAULT_EMBEDDING_DIM)
            if not isinstance(embedding_dim, int) or embedding_dim <= 0:
                raise ValueError("配置‘embedding_dim’必须是一个正整数。")

            fields = [
                FieldSchema(name=self.primary_field_name, dtype=DataType.INT64, is_primary=True, auto_id=True, description="唯一记忆标识符"),
                FieldSchema(name="personality_id", dtype=DataType.VARCHAR, max_length=256, description="与记忆关联的角色ID"),
                FieldSchema(name="session_id", dtype=DataType.VARCHAR, max_length=72, description="会话ID"),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096, description="记忆内容（摘要或片段）"),
                FieldSchema(name=self.vector_field_name, dtype=DataType.FLOAT_VECTOR, dim=embedding_dim, description="记忆的嵌入向量"),
                FieldSchema(name="create_time", dtype=DataType.INT64, description="创建记忆时的时间戳（Unix epoch）") # 如果没有提供，将自动添加到insert中
            ]

            self.collection_name = self.config.get('collection_name', DEFAULT_COLLECTION_NAME)
            self.collection_schema = CollectionSchema(
                fields=fields,
                description=f"长期记忆存储: {self.collection_name}",
                primary_field=PRIMARY_FIELD_NAME,
                enable_dynamic_field=self.config.get("enable_dynamic_field", False)
            )

            # 定义索引参数
            self.index_params = self.config.get("index_params", {
                "metric_type": "L2",       # 默认度量类型
                "index_type": "AUTOINDEX", # 默认索引类型（让Milvus选择）或指定为“IVF_FLAT”
                "params": {}               # 默认参数（AutoIndex不需要，其他可能需要）
                # 示例：IVF_FLAT: "params": {"nlist": 1024}
                # HNSW示例：“params”： {"M": 16, "efConstruction": 200}
            })
            # 定义搜索参数
            self.search_params = self.config.get("search_params", {
                "metric_type": self.index_params.get("metric_type", "L2"), # 必须匹配索引度量类型
                "params": {"nprobe": 10} # IVF_*的示例搜索参数，根据需要调整索引类型
                # HNSW示例：“params”： {"ef": 128}
            })

            self.output_fields_for_query = self.config.get("output_fields", DEFAULT_OUTPUT_FIELDS)
            # 如果用户配置没有明确要求，确保始终包含主键
            # if PRIMARY_FIELD_NAME not in self.output_fields_for_query:
            #     self.output_fields_for_query.append(PRIMARY_FIELD_NAME)

            self.logger.debug(f"集合模式定义 '{self.collection_name}' .")
            self.logger.debug(f"索引参数: {self.index_params}")
            self.logger.debug(f"搜索参数: {self.search_params}")
            self.logger.debug(f"输出字段: {self.output_fields_for_query}")

        except Exception as e:
            self.logger.error(f"初始化配置和架构失败: {e}", exc_info=True)
            raise # 重新引发以被__init__中的try-except捕获

    def _initialize_milvus(self):
        """初始化MilvusManager，连接并设置集合/索引。"""
        self.logger.debug("初始化Milvus连接和设置…")
        try:
            milvus_address = self.config.get("address")
            if not milvus_address:
                raise ValueError("Milvus 'address' （host:port或uri）未配置。")

            if milvus_address.startswith(("http://", "https://", "unix:")):
                connect_args = {"uri": milvus_address}
            else:
                host, port = parse_address(milvus_address)
                connect_args = {"host": host, "port": port}

            # 从配置中添加可选的连接参数
            for key in ["user", "password", "token", "secure", "db_name"]:
                if key in self.config:
                    connect_args[key] = self.config[key]
            connect_args["alias"] = self.config.get("connection_alias", DEFAULT_COLLECTION_NAME) # 使用配置或默认的别名，这配置未使用


            self.logger.info(f"试图用参数连接milvus: {connect_args}")
            self.milvus_manager = MilvusManager(**connect_args)

            if not self.milvus_manager or not self.milvus_manager.is_connected():
                raise ConnectionError("初始化或连接Milvus失败。处理步骤检查配置和服务状态.")

            self.logger.info(f"成功连接到Milvus (Alias: {connect_args['alias']}).")

            # --- 集合和索引设置 ---
            self._setup_milvus_collection_and_index()

        except Exception as e:
            self.logger.error(f"Milvus初始化或收集/索引设置失败: {e}", exc_info=True)
            self.milvus_manager = None # 确保失败时manager为None
            raise 

    def _setup_milvus_collection_and_index(self):
        """确保Milvus集合和索引存在并已加载。"""
        if not self.milvus_manager or not self.collection_schema:
            self.logger.error("无法设置Milvus集合/索引：管理器或架构未初始化。")
            raise RuntimeError("MilvusManager或CollectionSchema未准备好。")

        collection_name = self.collection_name

        # 如果存在collection，请检查Schema Consistency
        if self.milvus_manager.has_collection(collection_name):
            self.logger.info(f"集合“{collection_name}”已存在。检查模式一致性…")
            self._check_schema_consistency(collection_name, self.collection_schema)
            # ^^注意：_check_schema_consistency现在只记录警告。
        else:
            # 如果集合不存在，则创建集合
            self.logger.info(f"未找到集合“{collection_name}”。创建…")
            if not self.milvus_manager.create_collection(collection_name, self.collection_schema):
                raise RuntimeError(f"创建Milvus集合“{collection_name}”失败。")
            self.logger.info(f"成功创建集合“{collection_name}”。")
            # 创建集合后立即尝试创建索引
            self._ensure_milvus_index(collection_name)

        # 确保Index存在于（现已存在的）集合上
        self._ensure_milvus_index(collection_name)

        # 确保Collection已加载
        self.logger.info(f"确保集合‘{collection_name}’已加载…")
        if not self.milvus_manager.load_collection(collection_name):
            self.logger.error(f"加载集合“{collection_name}”失败。搜索功能可能不可用。")
        else:
            self.logger.info(f"已加载集合“{collection_name}”。")

    def _ensure_milvus_index(self, collection_name: str):
        """检查矢量索引，如果缺少则创建它。"""
        if not self.milvus_manager: return

        try:
            has_vector_index = False
            if self.milvus_manager.has_collection(collection_name):
                # 如果可用，使用has_index方法进行更健壮的检查，或者列出索引
                if self.milvus_manager.has_index(collection_name, index_name=None): # 首先检查是否存在任何索引
                    collection = self.milvus_manager.get_collection(collection_name)
                    if collection:
                        for index in collection.indexes:
                            if index.field_name == VECTOR_FIELD_NAME:
                                # TODO: 可选地检查索引参数是否匹配config？
                                self.logger.info(f"在集合“{collection_name}”上找到字段“{VECTOR_FIELD_NAME}”的现有索引。")
                                has_vector_index = True
                                break
                    else:
                        self.logger.warning(f"无法获取“{collection_name}”的收集对象以验证索引详细信息。")
                else:
                    self.logger.info(f"集合‘{collection_name}’已存在，但没有索引。")


            if not has_vector_index:
                self.logger.warning(f"在集合“{collection_name}”上找不到向量字段“{VECTOR_FIELD_NAME}”的索引。试图创建…")
                index_success = self.milvus_manager.create_index(
                    collection_name=collection_name,
                    field_name=VECTOR_FIELD_NAME,
                    index_params=self.index_params,
                    # index_name=f"{VECTOR_FIELD_NAME}_idx"
                )
                if not index_success:
                    self.logger.error(f"为字段“{VECTOR_FIELD_NAME}”创建索引失败。搜索性能将受到影响。")
                else:
                    self.logger.info(f"为字段“{VECTOR_FIELD_NAME}”发送索引创建请求。它会在后台中生成。")
            # else: 索引已存在
                # self.logger.info(f"集合“{collection_name}”上的向量字段“{VECTOR_FIELD_NAME}”已经有索引。")

        except Exception as e:
            self.logger.error(f"为“{collection_name}”检查或创建索引时出错：{e}", exc_info=True)
            raise
    
    def _initialize_components(self):
        """初始化非milvus组件，如上下文管理器和嵌入API。"""
        self.logger.debug("初始化其他组件…")
        try:
            self.context_manager = ConversationContextManager(
                max_turns=self.config.get("num_pairs", DEFAULT_MAX_TURNS),
                max_history_length=self.config.get("max_history_memory", DEFAULT_MAX_HISTORY)
            )
            self.logger.info("会话上下文管理器初始化。")
        except Exception as e:
            self.logger.error(f"初始化会话上下文管理器失败：{e}", exc_info=True)
            raise 

        try:
            self.ebd = OpenAIEmbeddingAPI(
                model=self.config.get("embedding_model"),
                api_key=self.config.get("embedding_key"),
                base_url=self.config.get("embedding_url")
            )
            # 初始化时测试连接
            self.ebd.test_connection() # 失败时引发异常
            self.logger.info("嵌入API初始化，连接测试成功。")
        except Exception as e:
            self.logger.error(f"嵌入API初始化或连接测试失败：{e}", exc_info=True)
            self.ebd = None # 确保失败时ebd为None
            raise
    
    # --- 模式检查的帮助器 ---
    def _check_schema_consistency(self, collection_name: str, expected_schema: CollectionSchema):
        """检查现有集合的 Schema 是否与预期一致 (简化版)。"""
        if not self.milvus_manager or not self.milvus_manager.has_collection(collection_name):
            # self.logger.info(f"集合 '{collection_name}' 不存在，无需检查一致性。")
            return True # 没有可供比较的现有集合

        try:
            collection = self.milvus_manager.get_collection(collection_name)
            if not collection:
                self.logger.error(f"无法获取集合 '{collection_name}' 以检查 schema。")
                return False # 视为不一致

            actual_schema = collection.schema
            expected_fields = {f.name: f for f in expected_schema.fields}
            actual_fields = {f.name: f for f in actual_schema.fields}

            consistent = True
            warnings = []

            # 检查期望字段
            for name, expected_field in expected_fields.items():
                if name not in actual_fields:
                    warnings.append(f"缺少字段 '{name}'")
                    consistent = False
                    continue
                actual_field = actual_fields[name]
                # 基本类型检查（可能需要对复杂类型/参数进行细化）
                if actual_field.dtype != expected_field.dtype:
                    # 允许VARCHAR的灵活性？检查dim中的向量。
                    is_vector = expected_field.dtype in [DataType.FLOAT_VECTOR, DataType.BINARY_VECTOR]
                    is_varchar = expected_field.dtype == DataType.VARCHAR

                    if is_vector:
                        expected_dim = expected_field.params.get('dim')
                        actual_dim = actual_field.params.get('dim')
                        if expected_dim != actual_dim:
                            warnings.append(f"字段 '{name}' 维度不匹配 (预期 {expected_dim}, 实际 {actual_dim})")
                            consistent = False
                    elif is_varchar:
                        expected_len = expected_field.params.get('max_length')
                        actual_len = actual_field.params.get('max_length')
                        if expected_len != actual_len:
                            # 但如果实际值更大，可能不会失败？
                            warnings.append(f"字段 '{name}' VARCHAR 长度不匹配 (预期 {expected_len}, 实际 {actual_len})")
                            # consistent = False # 判断这是否至关重要
                            
                    elif actual_field.dtype != expected_field.dtype:
                        warnings.append(f"字段 '{name}' 类型不匹配 (预期 {expected_field.dtype}, 实际 {actual_field.dtype})")
                        consistent = False

                # 查看主键/auto_id状态
                if actual_field.is_primary != expected_field.is_primary:
                    warnings.append(f"字段 '{name}' 主键状态不匹配")
                    consistent = False
                if expected_field.is_primary and actual_field.auto_id != expected_field.auto_id:
                    warnings.append(f"字段 '{name}' AutoID 状态不匹配")
                    consistent = False


            # 检查意外的额外字段
            for name in actual_fields:
                if name not in expected_fields:
                    warnings.append(f"发现预期之外的字段 '{name}'")
                    # TODO 判断这是否使它不一致

            if not consistent:
                self.logger.warning(f"集合 '{collection_name}' Schema 不一致: {'; '.join(warnings)}. 请手动检查或考虑重建集合。")
            else:
                self.logger.info(f"集合 '{collection_name}' Schema 与预期基本一致。")

            return consistent

        except Exception as e:
            self.logger.error(f"检查集合 '{collection_name}' schema 一致性时出错: {e}", exc_info=True)
            return False # 将错误视为不一致
