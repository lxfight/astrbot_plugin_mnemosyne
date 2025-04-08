# -*- coding: utf-8 -*-
"""
Mnemosyne 插件核心记忆操作逻辑
包括 RAG 查询、LLM 响应处理、记忆总结与存储。
"""

import re
import time
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Optional

from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.event import AstrMessageEvent
from pymilvus.exceptions import MilvusException

# 导入必要的类型和模块
from .constants import (
    VECTOR_FIELD_NAME,
    PRIMARY_FIELD_NAME,
    DEFAULT_TOP_K,
    DEFAULT_MILVUS_TIMEOUT,
    DEFAULT_PERSONA_ON_NONE,
)

# 类型提示，避免循环导入
if TYPE_CHECKING:
    from ..main import Mnemosyne


async def handle_query_memory(
    plugin: "Mnemosyne", event: AstrMessageEvent, req: ProviderRequest
):
    """
    处理 LLM 请求前的 RAG 检索逻辑。
    检索相关的长期记忆，并将其注入到 ProviderRequest 中。
    """
    logger = plugin.logger  # 使用主插件实例的 logger

    # --- 前置检查 ---
    if not plugin.milvus_manager or not plugin.milvus_manager.is_connected():
        logger.error("Milvus 服务未初始化或未连接，无法查询长期记忆。")
        return
    if not plugin.ebd:
        logger.error("Embedding API 未初始化，无法查询长期记忆。")
        return
    if not plugin.context_manager:
        logger.error("短期上下文管理器未初始化，无法记录用户输入。")
        # 即使无法记录短期上下文，也许仍应尝试查询长期记忆？取决于设计决策
        # return

    # --- 清理旧记忆标记 ---
    # 根据配置，从上下文中移除旧的 <Mnemosyne> 标记
    if plugin.config.get("clean_old_memory_markers", True):  # 添加配置开关
        i = 0
        for record in reversed(req.contexts):
            if record.get("role") == "user":
                i += 1
                # 如果配置为负数，则不清除
                contexts_memory_len = plugin.config.get(
                    "contexts_memory_len", 1
                )  # 默认只保留最近1条用户消息的记忆
                if contexts_memory_len < 0:
                    break
                # 清除超过配置数量的用户消息中的记忆标记
                if i > contexts_memory_len:
                    raw_content = record.get("content", "")
                    # 使用非贪婪匹配移除标记及其内容
                    clean_content = re.sub(
                        r"<Mnemosyne>.*?</Mnemosyne>\n?",
                        "",
                        raw_content,
                        flags=re.DOTALL,
                    ).strip()
                    if raw_content != clean_content:
                        record["content"] = clean_content
                        logger.debug(f"已清理旧的用户消息中的 <Mnemosyne> 标记。")
                    # 找到第一个需要清理的就够了，因为是从后往前遍历
                    break  # 清理完一个就退出

    try:
        # --- 获取会话和人格信息 ---
        session_id = await plugin.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        conversation = await plugin.context.conversation_manager.get_conversation(
            event.unified_msg_origin, session_id
        )
        persona_id = conversation.persona_id if conversation else None

        # 处理人格 ID 为空或特定占位符的情况
        if not persona_id or persona_id == "[%None]":
            default_persona = plugin.context.provider_manager.selected_default_persona
            persona_id = default_persona["name"] if default_persona else None
            if not persona_id:
                logger.warning(
                    f"当前会话 (ID: {session_id}) 及全局均未配置人格，将使用占位符 '{DEFAULT_PERSONA_ON_NONE}' 进行记忆操作（如果启用人格过滤）。"
                )
                # 根据配置决定是使用占位符还是完全不使用人格过滤
                if plugin.config.get("use_personality_filtering", False):
                    persona_id = DEFAULT_PERSONA_ON_NONE  # 使用占位符
                else:
                    persona_id = None  # 不按人格过滤
            else:
                logger.info(f"当前会话无人格，使用默认人格: '{persona_id}'")


        # --- 通过 历史上下文 获取短期上下文 & 触发总结 ---
        # 历史上下文长度 与 num_pairs 求余 ，
        contexts_len = len(req.contexts)
        # 获取 num_pairs 配置，如果为奇数，则+1
        num_pairs = plugin.config.get("num_pairs", 10)
        if num_pairs % 2 != 0 :
            num_pairs += 1
        # 对 历史上下文长度 取余 num_pairs ，如果等于 0 ，则触发总结
        new_contexts_len = contexts_len % num_pairs
        if contexts_len > 0 and (new_contexts_len == 0):
            logger.info(
                f"短期记忆达到阈值（LLM响应前），触发后台总结任务 (Session: {session_id[:8]}...)"
            )
            # 从 历史上下文 中，获取最新的 num_pairs 条 短期上下文
            contexts = req.contexts[-plugin.config.get("num_pairs", 10):]

            # 进行格式化处理
            memory_summary = plugin.context_manager.summarize_memory(
                session_id=session_id, role="assistant", contents=contexts
            )
            # 使用获取到的 persona_id (可能是 None 或占位符)
            asyncio.create_task(
                handle_summary_long_memory(
                    plugin, persona_id, session_id, memory_summary
                )
            )

        # 使用新逻辑，暂时注释
        # --- 记录用户消息到短期上下文 & 触发总结 ---
        # if plugin.context_manager:
        #     memory_summary_input = req.prompt  # 使用原始的用户输入进行总结可能更准确
        #     memory_summary = plugin.context_manager.add_message(
        #         session_id=session_id, role="user", content=memory_summary_input
        #     )
        #
        #     if memory_summary:
        #         logger.info(
        #             f"短期记忆达到阈值，触发后台总结任务 (Session: {session_id[:8]}...)"
        #         )
        #         # 确保 persona_id 正确传递 (可能是 None 或占位符)
        #         asyncio.create_task(
        #             handle_summary_long_memory(
        #                 plugin, persona_id, session_id, memory_summary
        #             )
        #         )
        # else:
        #     logger.warning("短期上下文管理器不可用，跳过记录用户消息和潜在的总结。")

        # --- RAG 搜索 ---
        detailed_results = []
        try:
            # 1. 向量化用户查询
            query_embeddings = plugin.ebd.get_embeddings(req.prompt)
            if not query_embeddings:
                logger.error("无法获取用户查询的 Embedding 向量。")
                return  # 无法进行向量搜索
            query_vector = query_embeddings[0]

            # 2. 构建搜索过滤器表达式
            filters = []
            # 会话过滤器 (通常是必须的)
            if session_id:
                filters.append(f'session_id == "{session_id}"')
            else:
                logger.warning("无法获取当前 session_id，将不按 session 过滤记忆！")
                # 可能需要根据策略决定是否继续搜索

            # 人格过滤器 (如果启用且 persona_id 有效)
            use_personality_filtering = plugin.config.get(
                "use_personality_filtering", False
            )
            effective_persona_id_for_filter = persona_id  # 使用前面处理过的 persona_id
            if use_personality_filtering and effective_persona_id_for_filter:
                filters.append(f'personality_id == "{effective_persona_id_for_filter}"')
                logger.debug(
                    f"将使用人格 '{effective_persona_id_for_filter}' 过滤记忆。"
                )
            elif use_personality_filtering:
                logger.debug(f"启用了人格过滤，但当前无有效人格 ID，不按人格过滤。")

            # 组合过滤器
            search_expression = (
                " and ".join(filters) if filters else ""
            )  # 如果没有过滤器，则为空字符串

            # 3. 执行 Milvus 搜索
            collection_name = plugin.collection_name
            top_k = plugin.config.get("top_k", DEFAULT_TOP_K)
            timeout_seconds = plugin.config.get(
                "milvus_search_timeout", DEFAULT_MILVUS_TIMEOUT
            )

            logger.info(
                f"开始在集合 '{collection_name}' 中搜索相关记忆 (TopK: {top_k}, Filter: '{search_expression or '无'}')"
            )

            try:
                # 使用 asyncio.wait_for 添加超时控制
                search_results = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,  # 使用默认线程池执行器
                        lambda: plugin.milvus_manager.search(
                            collection_name=collection_name,
                            query_vectors=[query_vector],  # 搜索 API 接收向量列表
                            vector_field=VECTOR_FIELD_NAME,
                            search_params=plugin.search_params,  # 使用初始化时定义的搜索参数
                            limit=top_k,
                            expression=search_expression,
                            output_fields=plugin.output_fields_for_query,  # 直接获取需要的字段
                            # consistency_level=plugin.config.get("consistency_level", "Bounded") # 可选：一致性级别
                        ),
                    ),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.error(f"Milvus 搜索超时 ({timeout_seconds} 秒)，操作已取消。")
                return  # 超时则不补充记忆
            except MilvusException as me:
                logger.error(f"Milvus 搜索操作失败: {me}", exc_info=True)
                return  # Milvus 操作错误，不补充记忆
            except Exception as e:
                logger.error(f"执行 Milvus 搜索时发生未知错误: {e}", exc_info=True)
                return  # 其他执行错误，不补充记忆

            # 4. 处理搜索结果
            if (
                not search_results or not search_results[0]
            ):  # search 返回 List[SearchResult], SearchResult 可能为空
                logger.info("向量搜索未找到相关记忆。")
            else:
                # search_results[0] 是针对第一个查询向量的结果 (SearchResult)
                hits = search_results[0]  # 获取 Hit 列表
                # detailed_results = [hit.entity.to_dict() for hit in hits if hasattr(hit, 'entity')] # 老版本 PyMilvus
                detailed_results = [
                    hit.entity.to_dict()["entity"] for hit in hits if hit.entity
                ]  # 假设 to_dict 返回 {'entity': {...}} 结构
                logger.debug(f"搜索命中 {len(detailed_results)} 条记录。")
                # logger.debug(f"详细结果: {detailed_results}") # 日志可能过长，谨慎开启

        except Exception as e:
            logger.error(f"处理长期记忆 RAG 查询时发生错误: {e}", exc_info=True)
            # 此处错误可能是 Embedding 获取失败等，也应终止后续处理
            return

        # 5. 格式化结果并注入到提示中
        if detailed_results:
            # 按时间戳对结果进行排序（如果需要，Milvus 搜索默认按距离排序）
            # sort_by_time = plugin.config.get("sort_rag_results_by_time", False)
            # if sort_by_time:
            #     detailed_results.sort(key=lambda x: x.get('create_time', 0), reverse=True) # 按时间降序

            long_memory_prefix = plugin.config.get(
                "long_memory_prefix", "<Mnemosyne>长期记忆片段："
            )
            long_memory_suffix = plugin.config.get("long_memory_suffix", "</Mnemosyne>")
            long_memory = f"{long_memory_prefix}\n"

            for result in detailed_results:
                content = result.get("content", "内容缺失")
                ts = result.get("create_time")
                # 尝试格式化时间，如果失败则显示原始时间戳或未知
                try:
                    time_str = (
                        datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                        if ts
                        else "未知时间"
                    )
                except (TypeError, ValueError):
                    time_str = f"时间戳: {ts}" if ts else "未知时间"

                memory_entry_format = plugin.config.get(
                    "memory_entry_format", "- [{time}] {content}"
                )
                long_memory += (
                    memory_entry_format.format(time=time_str, content=content) + "\n"
                )

            long_memory += long_memory_suffix

            logger.info(f"补充了 {len(detailed_results)} 条长期记忆到提示中。")
            logger.debug(f"补充内容:\n{long_memory}")  # 记录详细补充内容，可能较长

            # 根据策略决定如何注入（追加到用户提示、系统提示或作为独立上下文）
            injection_method = plugin.config.get(
                "memory_injection_method", "append_to_prompt"
            )  # append_to_prompt | prepend_to_prompt | system_prompt

            if injection_method == "append_to_prompt":
                req.prompt = (req.prompt or "") + "\n\n" + long_memory  # 添加换行符分隔
            elif injection_method == "prepend_to_prompt":
                req.prompt = long_memory + "\n\n" + (req.prompt or "")
            # elif injection_method == "system_prompt":
            #     # 注意：修改 system_prompt 可能需要 AstrBot 核心支持或特定 Provider 支持
            #     # req.system_prompt = (req.system_prompt or "") + "\n" + long_memory # 示例
            #     logger.warning("当前实现不支持将记忆注入 system_prompt，将追加到用户 prompt。")
            #     req.prompt = (req.prompt or "") + "\n\n" + long_memory
            else:  # 默认或未知方法，追加到用户提示
                logger.warning(
                    f"未知的记忆注入方法 '{injection_method}'，将默认追加到用户 prompt。"
                )
                req.prompt = (req.prompt or "") + "\n\n" + long_memory
        else:
            logger.info("未找到或获取到相关的长期记忆，不进行补充。")

    except Exception as e:
        # 捕获在获取会话 ID 等外部逻辑中可能发生的错误
        logger.error(f"处理 LLM 请求前的记忆查询流程失败: {e}", exc_info=True)


async def handle_on_llm_resp(
    plugin: "Mnemosyne", event: AstrMessageEvent, resp: LLMResponse
):
    """
    处理 LLM 响应后的逻辑。
    将 LLM 的回答添加到短期上下文中，并可能触发记忆总结。
    """
    logger = plugin.logger

    if not plugin.context_manager:
        logger.warning("短期上下文管理器未初始化，无法记录 LLM 响应。")
        return

    try:
        session_id = await plugin.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
        conversation = await plugin.context.conversation_manager.get_conversation(
            event.unified_msg_origin, session_id
        )
        persona_id = conversation.persona_id if conversation else None

        # 再次处理人格 ID
        if not persona_id or persona_id == "[%None]":
            default_persona = plugin.context.provider_manager.selected_default_persona
            persona_id = default_persona["name"] if default_persona else None
            if not persona_id:
                # 使用与 query 时相同的逻辑
                if plugin.config.get("use_personality_filtering", False):
                    persona_id = DEFAULT_PERSONA_ON_NONE
                else:
                    persona_id = None

        if not session_id:
            logger.error("无法获取当前 session_id，无法记录 LLM 响应到短期记忆。")
            return


        # 通过 历史上下文 获取短期上下文
        # 暂时注释 旧获取方法
        # 添加 LLM 响应到短期上下文
        # llm_response_text = resp.completion_text
        # memory_summary = plugin.context_manager.add_message(
        #     session_id=session_id, role="assistant", content=llm_response_text
        # )
        #
        # if memory_summary:
        #     logger.info(
        #         f"短期记忆达到阈值（LLM响应后），触发后台总结任务 (Session: {session_id[:8]}...)"
        #     )
        #     # 使用获取到的 persona_id (可能是 None 或占位符)
        #     asyncio.create_task(
        #         handle_summary_long_memory(
        #             plugin, persona_id, session_id, memory_summary
        #         )
        #     )

    except Exception as e:
        logger.error(f"处理 LLM 响应后的记忆记录失败: {e}", exc_info=True)


async def handle_summary_long_memory(
    plugin: "Mnemosyne", persona_id: Optional[str], session_id: str, memory_text: str
):
    """
    使用 LLM 总结短期对话历史形成长期记忆，并将其向量化后存入 Milvus。
    这是一个后台任务。
    """
    logger = plugin.logger

    # --- 前置检查 ---
    if not plugin.milvus_manager or not plugin.milvus_manager.is_connected():
        logger.error("Milvus 服务不可用，无法存储总结后的长期记忆。")
        return
    if not plugin.ebd:
        logger.error("Embedding API 不可用，无法向量化总结记忆。")
        return
    if not memory_text or not memory_text.strip():
        logger.warning("尝试总结空的或仅包含空白的记忆文本，跳过。")
        return

    # 获取 LLM Provider 用于总结
    try:
        llm_provider = plugin.context.get_using_provider()
        if not llm_provider:
            logger.error("无法获取用于总结记忆的 LLM Provider。")
            return
    except Exception as e:
        logger.error(f"获取 LLM Provider 时出错: {e}", exc_info=True)
        return

    try:
        # 1. 请求 LLM 进行总结
        long_memory_prompt = plugin.config.get(
            "long_memory_prompt",
            "请将以下多轮对话历史总结为一段简洁、客观、包含关键信息的长期记忆条目:",
        )
        # 添加上下文，指示 LLM 总结的是对话历史
        summary_context = [
            {"role": "system", "content": long_memory_prompt},
            {"role": "user", "content": memory_text},
        ]

        # 获取总结用的LLM配置，允许与主LLM不同
        summary_llm_config = plugin.config.get(
            "summary_llm_config", {}
        )  # 例如 {"model": "gpt-3.5-turbo", "max_tokens": 200}

        logger.debug(
            f"请求 LLM 总结短期记忆，提示: '{long_memory_prompt[:50]}...', 内容长度: {len(memory_text)}"
        )

        # 使用 text_chat 并传入可能的配置覆盖
        llm_response = await llm_provider.text_chat(
            prompt=memory_text,  # 主内容放在 prompt
            contexts=[
                {"role": "system", "content": long_memory_prompt}
            ],  # 引导指令放在 system context
            # model=summary_llm_config.get("model"), # 覆盖模型
            # max_tokens=summary_llm_config.get("max_tokens"), # 覆盖 token 限制
            **summary_llm_config,  # 传递其他可能的参数
        )
        logger.debug(f"LLM 总结响应原始数据: {llm_response}")  # 记录原始响应，便于调试

        # 2. 提取总结文本
        completion_text = None
        if isinstance(llm_response, LLMResponse):
            completion_text = llm_response.completion_text
            role = llm_response.role
        elif isinstance(llm_response, dict):  # 兼容可能的 dict 响应
            completion_text = llm_response.get("completion_text")
            role = llm_response.get("role")
        else:
            logger.error(f"LLM 总结返回了未知类型的数据: {type(llm_response)}")
            return

        if not completion_text or not completion_text.strip():
            logger.error(f"LLM 总结响应无效或内容为空。原始响应: {llm_response}")
            return
        # 可选：检查 LLM 返回的角色是否符合预期
        # if role != "assistant":
        #     logger.warning(f"LLM 总结响应的角色不是 'assistant' (而是 '{role}')。模型回复: {completion_text[:100]}...")

        summary_text = completion_text.strip()
        logger.info(f"LLM 成功生成记忆总结，长度: {len(summary_text)}")
        # logger.debug(f"总结内容: {summary_text}")

        # 3. 获取总结文本的 Embedding
        embedding_vectors = plugin.ebd.get_embeddings(summary_text)
        if not embedding_vectors:
            logger.error(f"无法获取总结文本的 Embedding: '{summary_text[:100]}...'")
            return
        embedding_vector = embedding_vectors[0]  # get_embeddings 返回列表

        # 4. 准备插入 Milvus 的数据
        collection_name = plugin.collection_name
        current_timestamp = int(time.time())  # 使用当前时间作为创建时间

        # 再次确认 persona_id (可能是 None 或占位符)
        effective_persona_id = (
            persona_id
            if persona_id
            else plugin.config.get(
                "default_persona_id_on_none", DEFAULT_PERSONA_ON_NONE
            )
        )

        # 构建插入数据结构，字段名需与 Schema 匹配
        data_to_insert = [
            {
                "personality_id": effective_persona_id,
                "session_id": session_id,
                "content": summary_text,  # 存储总结后的文本
                VECTOR_FIELD_NAME: embedding_vector,  # 使用常量定义的向量字段名
                "create_time": current_timestamp,
                # 主键 memory_id 是 auto_id，无需提供
            }
        ]
        # logger.debug(f"准备插入 Milvus 的数据: {data_to_insert}") # 可能包含向量，谨慎记录

        # 5. 执行插入操作
        logger.info(
            f"准备向集合 '{collection_name}' 插入 1 条总结记忆 (Persona: {effective_persona_id}, Session: {session_id[:8]}...)"
        )
        mutation_result = plugin.milvus_manager.insert(
            collection_name=collection_name,
            data=data_to_insert,
            # consistency_level=plugin.config.get("consistency_level", "Bounded") # 可选
        )

        if mutation_result and mutation_result.insert_count > 0:
            inserted_ids = mutation_result.primary_keys
            logger.info(f"成功插入总结记忆到 Milvus。插入 ID: {inserted_ids}")
            # 为了保证数据立即可查，可以选择在插入后执行 flush 操作
            flush_after_insert = plugin.config.get("flush_after_memory_insert", True)
            if flush_after_insert:
                try:
                    logger.debug(
                        f"正在刷新 (Flush) 集合 '{collection_name}' 以确保记忆立即可用..."
                    )
                    plugin.milvus_manager.flush([collection_name])
                    logger.debug(f"集合 '{collection_name}' 刷新完成。")
                except Exception as flush_err:
                    logger.error(
                        f"刷新集合 '{collection_name}' 时出错: {flush_err}",
                        exc_info=True,
                    )
        else:
            # 插入失败的原因可能需要看 Milvus 日志
            logger.error(
                f"插入总结记忆到 Milvus 失败。MutationResult: {mutation_result}. LLM 回复: {summary_text[:100]}..."
            )

    except Exception as e:
        logger.error(f"在总结或存储长期记忆的过程中发生严重错误: {e}", exc_info=True)
