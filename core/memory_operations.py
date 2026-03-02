"""
Mnemosyne 插件核心记忆操作逻辑
包括 RAG 查询、LLM 响应处理、记忆总结与存储。
"""

import asyncio
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pymilvus.exceptions import MilvusException

from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.log import LogManager

from .chatroom_parser import ChatroomContextParser
from .constants import (
    DEFAULT_MILVUS_TIMEOUT,
    DEFAULT_PERSONA_ON_NONE,
    DEFAULT_TOP_K,
    VECTOR_FIELD_NAME,
)
from .security_utils import (
    safe_build_milvus_expression,
    validate_personality_id,
    validate_session_id,
)
from .tools import (
    extract_query_keywords,
    format_context_to_string,
    pack_memory_content,
    remove_mnemosyne_tags,
    remove_system_content,
    remove_system_mnemosyne_tags,
    resolve_max_prompt_chars,
    split_memory_content_meta,
    strip_memory_meta,
    truncate_for_embedding,
)

# 类型提示，避免循环导入
if TYPE_CHECKING:
    from ..main import Mnemosyne

logger = LogManager.GetLogger(__name__)


def _extract_explicit_memory_content(prompt: str) -> str | None:
    """
    识别用户显式“记住”指令，提取需要写入长期记忆的正文。
    """
    if not isinstance(prompt, str):
        return None
    text = prompt.strip()
    if not text:
        return None

    patterns = [
        r"^\s*记住[:：\s]+(.+)$",
        r"^\s*请记住[:：\s]+(.+)$",
        r"^\s*帮我记住[:：\s]+(.+)$",
        r"^\s*remember(?:\s+this)?[:：\s]+(.+)$",
        r"^\s*please\s+remember[:：\s]+(.+)$",
    ]
    for pattern in patterns:
        matched = re.match(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if matched:
            content = matched.group(1).strip()
            if content:
                return content
    return None


def _collect_participants_from_context(context_history: list[dict] | None) -> list[str]:
    """
    从上下文中提取参与者 ID（仅统计 user 角色）。
    """
    if not isinstance(context_history, list):
        return []

    participants: list[str] = []
    seen: set[str] = set()
    for item in context_history:
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        speaker_id = metadata.get("speaker_id")
        if isinstance(speaker_id, str) and speaker_id.strip():
            normalized = speaker_id.strip()
            if normalized not in seen:
                participants.append(normalized)
                seen.add(normalized)
    return participants


def _build_lightweight_graph_metadata(
    summary_text: str,
    context_history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    生成轻量图谱元数据：实体、关系、参与者。
    """
    entities = extract_query_keywords(summary_text, min_token_len=2)[:20]
    relations: list[list[str]] = []
    relation_seen: set[tuple[str, str]] = set()

    # 基于句内共现构建轻量关系边（无额外数据库依赖）。
    sentences = re.split(r"[。！？!?；;\n]+", summary_text)
    for sentence in sentences:
        sentence_entities = extract_query_keywords(sentence, min_token_len=2)[:8]
        n = len(sentence_entities)
        for i in range(n):
            for j in range(i + 1, n):
                a = sentence_entities[i]
                b = sentence_entities[j]
                if a == b:
                    continue
                edge = (a, b) if a < b else (b, a)
                if edge in relation_seen:
                    continue
                relation_seen.add(edge)
                relations.append([edge[0], edge[1]])
                if len(relations) >= 40:
                    break
            if len(relations) >= 40:
                break
        if len(relations) >= 40:
            break

    return {
        "participants": _collect_participants_from_context(context_history),
        "entities": entities,
        "relations": relations,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _expand_graph_keywords(
    base_keywords: list[str], detailed_results: list[dict[str, Any]]
) -> list[str]:
    """
    依据候选记忆携带的 relations 做一次 one-hop 关键词扩展。
    """
    if not base_keywords:
        return []

    expanded: list[str] = []
    seen = set(base_keywords)
    for result in detailed_results:
        meta = result.get("_meta", {})
        if not isinstance(meta, dict):
            continue
        relations = meta.get("relations", [])
        if not isinstance(relations, list):
            continue
        for pair in relations:
            if (
                isinstance(pair, list)
                and len(pair) == 2
                and isinstance(pair[0], str)
                and isinstance(pair[1], str)
            ):
                a = pair[0].strip().lower()
                b = pair[1].strip().lower()
                if not a or not b:
                    continue
                if a in seen and b not in seen:
                    expanded.append(b)
                    seen.add(b)
                elif b in seen and a not in seen:
                    expanded.append(a)
                    seen.add(a)
    return expanded


def _post_process_search_results(
    plugin: "Mnemosyne",
    detailed_results: list[dict[str, Any]],
    query_text: str,
    sender_id: str | None,
) -> list[dict[str, Any]]:
    """
    对向量搜索结果进行后处理：
    1) 参与者过滤（可选）
    2) 关键词/轻量图谱重排（可选）
    """
    if not detailed_results:
        return detailed_results

    prepared: list[dict[str, Any]] = []
    for result in detailed_results:
        if not isinstance(result, dict):
            continue
        content = result.get("content", "")
        pure_content, meta = split_memory_content_meta(content)
        merged = dict(result)
        merged["content"] = pure_content
        merged["_meta"] = meta
        prepared.append(merged)

    # 参与者过滤
    normalized_sender_id = sender_id.strip() if isinstance(sender_id, str) else ""
    if plugin.config.get("use_participant_filtering", False) and normalized_sender_id:
        filtered: list[dict[str, Any]] = []
        for result in prepared:
            meta = result.get("_meta", {})
            participants = (
                meta.get("participants", []) if isinstance(meta, dict) else []
            )
            if not isinstance(participants, list) or not participants:
                # 无参与者信息时不强行过滤，保持兼容旧记录。
                filtered.append(result)
                continue
            normalized = {str(x).strip() for x in participants if str(x).strip()}
            if normalized_sender_id in normalized:
                filtered.append(result)
        if filtered:
            prepared = filtered

    # 关键词 + 图谱扩展重排
    keywords = extract_query_keywords(query_text, min_token_len=2)
    if not keywords:
        return prepared

    use_graph = plugin.config.get("use_lightweight_memory_graph", True)
    expanded = _expand_graph_keywords(keywords, prepared) if use_graph else []
    all_terms = keywords + [term for term in expanded if term not in keywords]

    def _semantic_score(item: dict[str, Any]) -> float:
        distance = item.get("_distance")
        if isinstance(distance, (int, float)):
            # 距离越小越相似，这里转为“分数越大越好”。
            return -float(distance)
        return 0.0

    scored = []
    for item in prepared:
        content = str(item.get("content", ""))
        content_l = content.lower()
        keyword_hits = 0
        for term in all_terms:
            term_l = term.lower()
            if term_l and term_l in content_l:
                keyword_hits += 1
        scored.append((keyword_hits, _semantic_score(item), item))

    if any(hit > 0 for hit, _, _ in scored):
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [item for _, _, item in scored]
    return prepared


async def handle_query_memory(
    plugin: "Mnemosyne", event: AstrMessageEvent, req: ProviderRequest
):
    """
    处理 LLM 请求前的 RAG 检索逻辑。
    检索相关的长期记忆，并将其注入到 ProviderRequest 中。
    """
    # logger = plugin.logger

    # --- 前置检查 ---
    if not await _check_rag_prerequisites(plugin):
        return

    try:
        # --- 获取会话和人格信息 ---
        persona_id = await _get_persona_id(plugin, event)
        # 直接使用 unified_msg_origin 作为 session_id，确保多Bot场景下的记忆隔离
        session_id = event.unified_msg_origin

        # 【新增】触发运行时自动迁移
        if session_id and ":" in session_id:
            # 异步触发迁移，不阻塞查询
            from .migration_utils import migrate_session_data_if_needed

            asyncio.create_task(
                migrate_session_data_if_needed(
                    plugin, session_id, plugin.collection_name
                )
            )

        # M12 修复: 加强 session_id 空值检查，确保类型和内容都有效
        if (
            session_id is None
            or not isinstance(session_id, str)
            or not session_id.strip()
        ):
            logger.error(
                f"无法获取有效的 session_id (值: {session_id}, 类型: {type(session_id).__name__})，跳过记忆查询操作"
            )
            return

        # 检查 context_manager 和 msg_counter 是否可用
        if not plugin.context_manager or not plugin.msg_counter:
            logger.warning("context_manager 或 msg_counter 不可用，跳过记忆查询")
            return

        # 在最早阶段清理 Mnemosyne 标签，避免将带标签/异常结构的 contexts 写入会话历史。
        clean_contexts(plugin, req)

        # 判断是否在历史会话管理器中，如果不在，则进行初始化
        if session_id not in plugin.context_manager.conversations:
            plugin.context_manager.init_conv(session_id, req.contexts, event)

        # 生成供“插件内部记忆/向量化”使用的安全用户文本：
        # - AstrBot 可能在纯图片消息时令 prompt=None，此处用占位符避免报错
        # - 不修改 req.prompt，避免影响实际发给 LLM 的内容
        raw_prompt = req.prompt if isinstance(req.prompt, str) else ""
        safe_user_prompt = raw_prompt
        if not safe_user_prompt.strip() and getattr(req, "image_urls", None):
            safe_user_prompt = "[图片]"
        # 防御：极端情况下避免将超长文本写入记忆/embedding
        max_prompt_chars = resolve_max_prompt_chars(plugin.config, default=4000)
        original_prompt_len = len(safe_user_prompt)
        safe_user_prompt, prompt_was_truncated = truncate_for_embedding(
            safe_user_prompt,
            max_prompt_chars,
            append_suffix=True,
        )
        if prompt_was_truncated:
            logger.warning(
                f"用户输入过长 ({original_prompt_len} chars)，已截断到 {max_prompt_chars} chars。"
            )

        # 添加用户消息（写入插件上下文管理器）
        sender_id = str(event.get_sender_id()) if event.get_sender_id() else ""
        plugin.context_manager.add_message(
            session_id,
            "user",
            safe_user_prompt,
            metadata={"speaker_id": sender_id},
        )
        # 计数器+1
        plugin.msg_counter.increment_counter(session_id)

        # --- RAG 搜索 ---
        detailed_results = []
        try:
            # 1. 向量化用户查询
            # 使用 AstrBot EmbeddingProvider（异步）
            try:
                # 等待 Embedding Provider 就绪
                if (
                    not plugin.embedding_provider
                    and not plugin._embedding_provider_ready
                ):
                    logger.warning("Embedding Provider 不可用，无法执行 RAG 搜索")
                    return

                # ===== 提取真实用户消息用于 RAG 搜索 =====
                # 自动检测并提取（如果不是特殊格式则返回原值）
                actual_query = ChatroomContextParser.extract_actual_message(
                    safe_user_prompt
                )

                if actual_query != safe_user_prompt:
                    logger.info(
                        f"检测到群聊上下文格式，已提取真实消息用于 RAG 搜索 "
                        f"(原始: {len(safe_user_prompt)}字符 → 提取: {len(actual_query)}字符)"
                    )

                # 支持显式记忆触发：仅在强触发语句下执行，默认关闭以避免误触。
                if plugin.config.get("enable_explicit_memory_capture", False):
                    explicit_content = _extract_explicit_memory_content(actual_query)
                    if explicit_content:
                        stored = await store_manual_memory(
                            plugin=plugin,
                            event=event,
                            memory_content=explicit_content,
                            source="explicit_trigger",
                        )
                        if stored:
                            logger.info("已根据显式“记住”触发写入长期记忆。")

                if len(actual_query) > max_prompt_chars:
                    logger.warning(
                        f"RAG 查询文本过长 ({len(actual_query)} chars)，按配置截断到 {max_prompt_chars} chars。"
                    )
                    actual_query = actual_query[:max_prompt_chars]

                # 使用 AstrBot EmbeddingProvider 的 embed 方法
                if plugin.embedding_provider:
                    # 使用提取的真实消息进行向量化
                    query_vector = await plugin.embedding_provider.get_embedding(
                        actual_query
                    )
                else:
                    logger.error("Embedding Provider 未正确初始化")
                    return

                if not query_vector:
                    logger.error("无法获取用户查询的 Embedding 向量。")
                    return

            except ConnectionError as e:
                logger.error(f"网络连接错误，无法获取 Embedding: {e}", exc_info=True)
                return
            except ValueError as e:
                logger.error(f"输入参数错误，无法获取 Embedding: {e}", exc_info=True)
                return
            except RuntimeError as e:
                logger.error(f"运行时错误，无法获取 Embedding: {e}", exc_info=True)
                return
            except Exception as e:
                logger.error(f"获取 Embedding 时发生未知错误: {e}", exc_info=True)
                return

            # 2. 执行 Milvus 搜索
            detailed_results = await _perform_milvus_search(
                plugin,
                query_vector,
                session_id,
                persona_id,
                query_text=actual_query,
                sender_id=sender_id,
            )

            # 3. 格式化结果并注入到提示中
            if detailed_results:
                _format_and_inject_memory(plugin, detailed_results, req)

        except Exception as e:
            logger.error(f"处理长期记忆 RAG 查询时发生错误: {e}", exc_info=True)
            return

    except Exception as e:
        logger.error(f"处理 LLM 请求前的记忆查询流程失败: {e}", exc_info=True)


async def handle_on_llm_resp(
    plugin: "Mnemosyne", event: AstrMessageEvent, resp: LLMResponse
):
    """
    处理 LLM 响应后的逻辑。更新计数器。
    """
    if resp.role != "assistant":
        logger.warning("LLM 响应不是助手角色，不进行记录。")
        return

    # 检查是否有 context_manager 和 msg_counter
    if not plugin.context_manager or not plugin.msg_counter:
        logger.warning("context_manager 或 msg_counter 不可用，跳过记忆记录")
        return

    try:
        # 直接使用 unified_msg_origin 作为 session_id
        session_id = event.unified_msg_origin
        if not session_id:
            logger.error("无法获取当前 session_id,无法记录 LLM 响应到Mnemosyne。")
            return
        persona_id = await _get_persona_id(plugin, event)

        # 判断是否需要总结
        await _check_and_trigger_summary(
            plugin,
            session_id,
            plugin.context_manager.get_history(session_id),
            persona_id,
        )

        logger.debug(f"返回的内容：{resp.completion_text}")
        plugin.context_manager.add_message(
            session_id,
            "assistant",
            resp.completion_text,
            metadata={"speaker_id": "assistant"},
        )
        plugin.msg_counter.increment_counter(session_id)

    except Exception as e:
        logger.error(f"处理 LLM 响应后的记忆记录失败: {e}", exc_info=True)


# 记忆查询 (RAG) 相关函数
async def _check_rag_prerequisites(plugin: "Mnemosyne") -> bool:
    """
    检查 RAG 查询的前提条件是否满足。

    Args:
        plugin: Mnemosyne 插件实例。

    Returns:
        True 如果前提条件满足，False 否则。
    """
    # logger = plugin.logger
    if not plugin.milvus_manager:
        logger.warning("Milvus 管理器未初始化，无法查询长期记忆。")
        return False
    if not plugin.milvus_manager.is_connected():
        logger.warning("Milvus 服务未连接，无法查询长期记忆。")
        return False
    # 检查 Embedding Provider 是否就绪，支持延迟加载
    if not plugin.embedding_provider and not plugin._embedding_provider_ready:
        logger.warning("Embedding Provider 未初始化，部分功能可能受限。")
        return False
    if not plugin.msg_counter:
        logger.error("消息计数器未初始化，将无法实现记忆总结")
        return False
    return True


async def _get_persona_id(plugin: "Mnemosyne", event: AstrMessageEvent) -> str | None:
    """
    获取当前会话的人格 ID。

    Args:
        plugin: Mnemosyne 插件实例。
        event: 消息事件。

    Returns:
        人格 ID 字符串，如果没有人格或发生错误则为 None。
    """
    # logger = plugin.logger
    # 获取 conversation_id 用于获取人格配置
    conversation_id = (
        await plugin.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin
        )
    )
    conversation = await plugin.context.conversation_manager.get_conversation(
        event.unified_msg_origin, str(conversation_id)
    )
    persona_id = conversation.persona_id if conversation else None

    if not persona_id or persona_id == "[%None]":
        if plugin.config.get("personality_fallback", False):
            # 尝试获取默认人格
            try:
                fallback_id = (
                    (plugin.context.get_config(event.unified_msg_origin) or {})
                    .get("provider_settings", {})
                    .get("default_personality", DEFAULT_PERSONA_ON_NONE)
                )
                if not fallback_id or fallback_id == "[%None]":
                    fallback_id = DEFAULT_PERSONA_ON_NONE
                message = f"当前会话 (ID: {event.unified_msg_origin}) 未配置人格，将使用默认人格 '{fallback_id}' 进行记忆操作（如果启用人格过滤）。"
            except Exception as e:
                logger.error(f"获取默认人格失败: {e}，回退到占位符")
                fallback_id = DEFAULT_PERSONA_ON_NONE
                message = f"当前会话 (ID: {event.unified_msg_origin}) 未配置人格，将使用占位符 '{fallback_id}' 进行记忆操作（如果启用人格过滤）。"
        else:
            # 不使用默认人格，避免记忆错乱
            fallback_id = DEFAULT_PERSONA_ON_NONE
            message = f"当前会话 (ID: {event.unified_msg_origin}) 未配置人格，将使用占位符 '{fallback_id}' 进行记忆操作（如果启用人格过滤）。"

        logger.warning(message)

        if plugin.config.get("use_personality_filtering", False):
            persona_id = fallback_id
        else:
            persona_id = None
    return persona_id


async def _check_and_trigger_summary(
    plugin: "Mnemosyne",
    session_id: str,
    context: list[dict],
    persona_id: str | None,
):
    """
    检查是否满足总结条件并触发总结任务。

    Args:
        plugin: Mnemosyne 插件实例。
        session_id: 会话 ID。
        context: 请求上下文列表。
        persona_id: 人格 ID.
    """
    # M24 修复: 添加 msg_counter 的类型检查
    # num_pairs 是对话轮数，msg_counter 计数的是消息条数（一问一答=2条消息）
    # 所以需要用 num_pairs * 2 来比较
    num_pairs = plugin.config.get("num_pairs", 5)
    if (
        plugin.msg_counter
        and plugin.msg_counter.adjust_counter_if_necessary(session_id, context)
        and plugin.msg_counter.get_counter(session_id) >= num_pairs * 2
    ):
        logger.info(f"对话已达到 {num_pairs} 轮，开始总结历史对话...")
        # M24 修复: 添加类型忽略，context 来自运行时的上下文
        history_contents = format_context_to_string(
            context,  # type: ignore
            num_pairs * 2,  # 传递消息条数而不是轮数
        )

        # M19 修复: 为后台任务添加异常处理回调
        task = asyncio.create_task(
            handle_summary_long_memory(
                plugin,
                persona_id,
                session_id,
                history_contents,
                context_history=context,
            )
        )

        def task_done_callback(t: asyncio.Task):
            """后台任务完成时的回调，用于捕获未处理的异常"""
            try:
                # 获取任务结果，如果有异常会在这里抛出
                t.result()
            except asyncio.CancelledError:
                logger.info(f"总结任务被取消 (session: {session_id})")
            except Exception as e:
                logger.error(
                    f"后台总结任务执行失败 (session: {session_id}): {e}", exc_info=True
                )

        task.add_done_callback(task_done_callback)
        logger.info("总结历史对话任务已提交到后台执行。")
        # M24 修复: 添加类型检查
        if plugin.msg_counter:
            plugin.msg_counter.reset_counter(session_id)


async def _perform_milvus_search(
    plugin: "Mnemosyne",
    query_vector: list[float],
    session_id: str | None,
    persona_id: str | None,
    query_text: str = "",
    sender_id: str | None = None,
) -> list[dict] | None:
    """
    执行 Milvus 向量搜索。

    Args:
        plugin: Mnemosyne 插件实例。
        query_vector: 查询向量。
        session_id: 会话 ID。
        persona_id: 人格 ID。

    Returns:
        Milvus 搜索结果列表，如果没有找到或出错则为 None。
    """
    # logger = plugin.logger
    # 防止没有过滤条件引发的潜在错误
    filters = ["memory_id > 0"]

    # 检查是否启用了会话过滤
    use_session_filtering = plugin.config.get("use_session_filtering", True)

    if use_session_filtering:
        if session_id:
            # 安全检查：验证 session_id 格式
            if not validate_session_id(session_id):
                logger.error(f"session_id 格式验证失败: {session_id}")
                return None

            # 使用安全的表达式构建方法
            try:
                session_filter = safe_build_milvus_expression(
                    "session_id", session_id, "=="
                )
                filters.append(session_filter)
                logger.debug(f"已启用会话过滤，将使用会话 '{session_id}' 过滤记忆。")
            except ValueError as e:
                logger.error(f"构建 session_id 过滤表达式失败: {e}")
                return None
        else:
            logger.warning("无法获取当前 session_id，将不按 session 过滤记忆！")
    else:
        logger.info("会话过滤已禁用，将在所有会话中搜索记忆。")

    use_personality_filtering = plugin.config.get("use_personality_filtering", False)
    effective_persona_id_for_filter = persona_id
    if use_personality_filtering and effective_persona_id_for_filter:
        # 安全检查：验证 personality_id 格式
        if not validate_personality_id(effective_persona_id_for_filter):
            logger.warning(
                f"personality_id 格式验证失败: {effective_persona_id_for_filter}，跳过人格过滤"
            )
        else:
            # 使用安全的表达式构建方法
            try:
                persona_filter = safe_build_milvus_expression(
                    "personality_id", effective_persona_id_for_filter, "=="
                )
                filters.append(persona_filter)
                logger.debug(
                    f"将使用人格 '{effective_persona_id_for_filter}' 过滤记忆。"
                )
            except ValueError as e:
                logger.error(f"构建 personality_id 过滤表达式失败: {e}")
    elif use_personality_filtering:
        logger.debug("启用了人格过滤，但当前无有效人格 ID，不按人格过滤。")

    search_expression = " and ".join(filters) if filters else ""
    collection_name = plugin.collection_name
    top_k = plugin.config.get("top_k", DEFAULT_TOP_K)
    timeout_seconds = plugin.config.get("milvus_search_timeout", DEFAULT_MILVUS_TIMEOUT)

    candidate_limit = min(max(top_k * 4, top_k), 60)
    logger.info(
        f"开始在集合 '{collection_name}' 中搜索相关记忆 (TopK: {top_k}, Candidates: {candidate_limit}, Filter: '{search_expression or '无'}')"
    )

    # M24 修复: 添加 milvus_manager 的类型检查
    if not plugin.milvus_manager:
        logger.error("Milvus 管理器不可用")
        return None

    try:
        search_results = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: plugin.milvus_manager.search(  # type: ignore
                    collection_name=collection_name,
                    query_vectors=[query_vector],
                    vector_field=VECTOR_FIELD_NAME,
                    search_params=plugin.search_params,
                    limit=candidate_limit,
                    expression=search_expression,
                    output_fields=plugin.output_fields_for_query,
                ),
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.error(f"Milvus 搜索超时 ({timeout_seconds} 秒)，操作已取消。")
        return None
    except MilvusException as me:
        logger.error(f"Milvus 搜索操作失败: {me}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"执行 Milvus 搜索时发生未知错误: {e}", exc_info=True)
        return None

    if not search_results or not search_results[0]:
        logger.info("向量搜索未找到相关记忆。")
        return None
    else:
        # 从 search_results 中获取 Hits 对象
        hits = search_results[0]
        # 调用新的辅助函数来处理 Hits 对象并提取详细结果
        detailed_results = _process_milvus_hits(hits)
        if not detailed_results:
            return detailed_results

        post_processed = _post_process_search_results(
            plugin=plugin,
            detailed_results=detailed_results,
            query_text=query_text,
            sender_id=sender_id,
        )
        # 最终返回 top_k 条
        return post_processed[:top_k]


def _process_milvus_hits(hits) -> list[dict[str, Any]]:
    """
    处理 Milvus SearchResults 中的 Hits 对象，使用基于索引的遍历方式
    提取有效的记忆实体数据。

    Args:
        hits: 从 Milvus 搜索结果 search_results[0] 中获取的 Hits 对象。

    Returns:
        一个包含提取到的记忆实体字典的列表。如果没有任何有效实体被提取，
        则返回空列表 []。
    """
    detailed_results: list[dict[str, Any]] = []  # 初始化结果列表，指定类型

    # 使用索引遍历 hits 对象，以绕过 SequenceIterator 的迭代问题
    if hits:  # 确保 hits 对象不是空的或 None
        try:
            num_hits = len(hits)  # 获取命中数量
            logger.debug(f"Milvus 返回了 {num_hits} 条原始命中结果。")

            # 使用索引进行遍历
            for i in range(num_hits):
                try:
                    hit = hits[i]  # 通过索引获取单个 Hit 对象

                    # 检查 hit 对象及其 entity 属性是否存在且有效
                    # 使用 hasattr 更健壮，避免在 entity 属性不存在时报错
                    if hit and hasattr(hit, "entity") and hit.entity:
                        # 提取 entity 数据，使用 .get() 避免 KeyError
                        # 假设 entity.to_dict() 返回的字典中有 "entity" 键
                        entity_data = hit.entity.to_dict().get("entity")
                        # 如果成功提取到数据，则添加到结果列表
                        if entity_data:
                            # 附带 Milvus 距离信息用于后续关键词/图谱重排
                            if isinstance(entity_data, dict):
                                entity_data = dict(entity_data)
                                distance = getattr(hit, "distance", None)
                                if isinstance(distance, (int, float)):
                                    entity_data["_distance"] = float(distance)
                            detailed_results.append(entity_data)
                        else:
                            # 如果 entity 存在但提取的数据为空，可能是数据结构问题
                            logger.warning(
                                f"命中结果索引 {i} 处的 entity 数据为空或无效，已跳过。"
                            )
                    else:
                        # 如果 hit 或 entity 无效，则跳过
                        logger.debug(f"命中结果索引 {i} 处对象或 entity 无效，已跳过。")

                except Exception as e:
                    # 处理访问或处理单个 hit 时可能出现的错误
                    logger.error(
                        f"处理索引 {i} 处的命中结果时发生错误: {e}", exc_info=True
                    )
                    # 发生错误时继续处理下一个 hit，不中断整个流程

        except Exception as e:
            # 处理获取长度或设置循环时可能出现的更严重的错误
            # 如果在这里发生错误，detailed_results 可能不完整或为空
            logger.error(f"执行基于索引的命中结果处理时发生错误: {e}", exc_info=True)

    # 记录成功处理并提取记忆的记录数
    logger.debug(f"成功处理并提取记忆的记录数: {len(detailed_results)} 条。")

    return detailed_results


# LLM 响应处理相关函数
def _format_and_inject_memory(
    plugin: "Mnemosyne", detailed_results: list[dict], req: ProviderRequest
):
    """
    格式化搜索结果并注入到 ProviderRequest 中。

    Args:
        plugin: Mnemosyne 插件实例。
        detailed_results: 详细的搜索结果列表。
        req: ProviderRequest 对象。
    """
    # logger = plugin.logger
    if not detailed_results:
        logger.info("未找到或获取到相关的长期记忆，不进行补充。")
        return

    long_memory_prefix = plugin.config.get(
        "long_memory_prefix", "<Mnemosyne> 长期记忆片段："
    )
    long_memory_suffix = plugin.config.get("long_memory_suffix", "</Mnemosyne>")
    long_memory = f"{long_memory_prefix}\n"

    for result in detailed_results:
        content = strip_memory_meta(str(result.get("content", "内容缺失")))
        ts = result.get("create_time")
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
        long_memory += memory_entry_format.format(time=time_str, content=content) + "\n"

    long_memory += long_memory_suffix

    logger.info(f"补充了 {len(detailed_results)} 条长期记忆到提示中。")
    logger.debug(f"补充内容:\n{long_memory}")

    injection_method = plugin.config.get("memory_injection_method", "user_prompt")
    injection_position = plugin.config.get("memory_injection_position", "prepend")
    if injection_position not in {"prepend", "append"}:
        injection_position = "prepend"

    # 清理插入的长期记忆内容
    clean_contexts(plugin, req)
    if injection_method == "user_prompt":
        current_prompt = req.prompt if isinstance(req.prompt, str) else ""
        if injection_position == "append":
            req.prompt = current_prompt + "\n" + long_memory
        else:
            req.prompt = long_memory + "\n" + current_prompt

    elif injection_method == "system_prompt":
        current_system_prompt = (
            req.system_prompt if isinstance(req.system_prompt, str) else ""
        )
        if injection_position == "append":
            req.system_prompt = current_system_prompt + long_memory
        else:
            req.system_prompt = long_memory + current_system_prompt

    elif injection_method == "insert_system_prompt":
        payload = {"role": "system", "content": long_memory}
        if injection_position == "append":
            req.contexts.append(payload)
        else:
            req.contexts.insert(0, payload)

    else:
        logger.warning(
            f"未知的记忆注入方法 '{injection_method}'，将默认追加到用户 prompt。"
        )
        current_prompt = req.prompt if isinstance(req.prompt, str) else ""
        req.prompt = long_memory + "\n" + current_prompt


# 删除补充的长期记忆函数
def clean_contexts(plugin: "Mnemosyne", req: ProviderRequest):
    """
    删除长期记忆中的标签
    """
    injection_method = plugin.config.get("memory_injection_method", "user_prompt")
    contexts_memory_len = plugin.config.get("contexts_memory_len", 0)
    if injection_method == "user_prompt":
        req.contexts = remove_mnemosyne_tags(req.contexts, contexts_memory_len)
    elif injection_method == "system_prompt":
        req.system_prompt = remove_system_mnemosyne_tags(
            req.system_prompt, contexts_memory_len
        )
    elif injection_method == "insert_system_prompt":
        req.contexts = remove_system_content(req.contexts, contexts_memory_len)
    return


# 记忆总结相关函数
async def _check_summary_prerequisites(plugin: "Mnemosyne", memory_text: str) -> bool:
    """
    检查记忆总结的前提条件是否满足。

    Args:
        plugin: Mnemosyne 插件实例。
        memory_text: 记忆文本。

    Returns:
        True 如果前提条件满足，False 否则。
    """
    # logger = plugin.logger
    if not plugin.milvus_manager or not plugin.milvus_manager.is_connected():
        logger.error("Milvus 服务不可用，无法存储总结后的长期记忆。")
        return False
    if not plugin.embedding_provider:
        logger.error("Embedding Provider 不可用，无法向量化总结记忆。")
        return False
    if not memory_text or not memory_text.strip():
        logger.warning("尝试总结空的或仅包含空白的记忆文本，跳过。")
        return False
    return True


async def _get_summary_llm_response(
    plugin: "Mnemosyne", memory_text: str
) -> LLMResponse | None:
    """
    请求 LLM 进行记忆总结。

    Args:
        plugin: Mnemosyne 插件实例。
        memory_text: 需要总结的记忆文本。

    Returns:
        LLMResponse 对象，如果请求失败则为 None。
    """
    # logger = plugin.logger
    llm_provider = plugin.provider
    # TODO: 优化LLM Provider获取逻辑，确保在plugin.provider不可用时能正确回退到当前使用的Provider
    try:
        if not llm_provider:
            # 如果plugin.provider不正确，在这时候，使用当前使用的LLM服务商，避免错误
            llm_provider = plugin.context.get_using_provider()
            if not llm_provider:
                logger.error("无法获取用于总结记忆的 LLM Provider。")
                return None
    except Exception as e:
        logger.error(f"获取 LLM Provider 时出错: {e}", exc_info=True)
        return None

    long_memory_prompt = plugin.config.get(
        "long_memory_prompt",
        "请将以下多轮对话历史总结为一段简洁、客观、包含关键信息的长期记忆条目:",
    )
    summary_llm_config = plugin.config.get("summary_llm_config", {})

    logger.debug(
        f"请求 LLM 总结短期记忆，提示: '{long_memory_prompt[:50]}...', 内容长度: {len(memory_text)}"
    )

    try:
        summary_contexts = [{"role": "system", "content": long_memory_prompt}]
        if plugin.config.get("use_summary_time_anchor", True):
            now_str = datetime.now().astimezone().isoformat(timespec="seconds")
            summary_contexts.append(
                {
                    "role": "system",
                    "content": (
                        f"当前绝对时间：{now_str}。"
                        "如果原始对话未明确给出具体日期/年份，禁止臆造精确日期；"
                        "请使用“近期/之前/后来”等相对表达。"
                    ),
                }
            )

        # M24 修复: 添加 text_chat 方法的类型忽略
        llm_response = await llm_provider.text_chat(  # type: ignore
            prompt=memory_text,
            contexts=summary_contexts,
            **summary_llm_config,
        )
        logger.debug(f"LLM 总结响应原始数据: {llm_response}")
        return llm_response
    except Exception as e:
        logger.error(f"LLM 总结请求失败: {e}", exc_info=True)
        return None


def _extract_summary_text(plugin: "Mnemosyne", llm_response: LLMResponse) -> str | None:
    """
    从 LLM 响应中提取总结文本并进行校验。

    Args:
        plugin: Mnemosyne 插件实例。
        llm_response: LLMResponse 对象。

    Returns:
        总结文本字符串，如果提取失败则为 None。
    """
    # logger = plugin.logger
    completion_text = None
    if isinstance(llm_response, LLMResponse):
        completion_text = llm_response.completion_text
        # role = llm_response.role
    elif isinstance(llm_response, dict):
        completion_text = llm_response.get("completion_text")
        # role = llm_response.get("role")
    else:
        logger.error(f"LLM 总结返回了未知类型的数据: {type(llm_response)}")
        return None

    if not completion_text or not completion_text.strip():
        logger.error(f"LLM 总结响应无效或内容为空。原始响应: {llm_response}")
        return None

    summary_text = completion_text.strip()
    logger.info(f"LLM 成功生成记忆总结，长度: {len(summary_text)}")
    return summary_text


async def _store_summary_to_milvus(
    plugin: "Mnemosyne",
    persona_id: str | None,
    session_id: str,
    summary_text: str,
    embedding_vector: list[float],
) -> bool:
    """
    将总结文本和向量存储到 Milvus 中。

    Args:
        plugin: Mnemosyne 插件实例。
        persona_id: 人格 ID。
        session_id: 会话 ID。
        summary_text: 总结文本。
        embedding_vector: 总结文本的 Embedding 向量。
    """
    # logger = plugin.logger
    collection_name = plugin.collection_name
    current_timestamp = int(time.time())

    effective_persona_id = (
        persona_id
        if persona_id
        else plugin.config.get("default_persona_id_on_none", DEFAULT_PERSONA_ON_NONE)
    )

    data_to_insert = [
        {
            "personality_id": effective_persona_id,
            "session_id": session_id,
            "content": summary_text,
            VECTOR_FIELD_NAME: embedding_vector,
            "create_time": current_timestamp,
        }
    ]

    logger.info(
        f"准备向集合 '{collection_name}' 插入 1 条总结记忆 (Persona: {effective_persona_id}, Session: {session_id[:8]}...)"
    )
    # mutation_result = plugin.milvus_manager.insert(
    #     collection_name=collection_name,
    #     data=data_to_insert,
    # )
    # --- 修改 insert 调用 ---
    loop = asyncio.get_event_loop()
    mutation_result = None

    # M24 修复: 添加 milvus_manager 的类型检查
    if not plugin.milvus_manager:
        logger.error("Milvus 管理器不可用")
        return False

    try:
        # M24 修复: 定义插入函数避免类型检查问题
        def _insert_data():
            return plugin.milvus_manager.insert(  # type: ignore
                collection_name=collection_name,
                data=data_to_insert,  # type: ignore
            )

        mutation_result = await loop.run_in_executor(
            None,  # 使用默认线程池
            _insert_data,
        )
    except (MilvusException, ConnectionError, ValueError) as e:
        logger.error(f"向 Milvus 插入总结记忆时出错: {e}", exc_info=True)
    finally:
        # 确保资源清理和错误日志记录
        if mutation_result is None:
            logger.error(
                f"Milvus 插入操作失败，未返回结果。集合: {collection_name}, 数据: {summary_text[:100]}..."
            )
        else:
            logger.debug("Milvus 插入操作完成，正在进行资源清理。")

    if mutation_result and mutation_result.insert_count > 0:
        inserted_ids = mutation_result.primary_keys
        logger.info(f"成功插入总结记忆到 Milvus。插入 ID: {inserted_ids}")

        try:
            logger.debug(
                f"正在刷新 (Flush) 集合 '{collection_name}' 以确保记忆立即可用..."
            )

            # plugin.milvus_manager.flush([collection_name])
            # M24 修复: 定义刷新函数避免类型检查问题
            def _flush_collection():
                return plugin.milvus_manager.flush([collection_name])  # type: ignore

            await loop.run_in_executor(
                None,  # 使用默认线程池
                _flush_collection,
            )
            logger.debug(f"集合 '{collection_name}' 刷新完成。")
            return True

        except Exception as flush_err:
            logger.error(
                f"刷新集合 '{collection_name}' 时出错: {flush_err}",
                exc_info=True,
            )
            return False
    else:
        logger.error(
            f"插入总结记忆到 Milvus 失败。MutationResult: {mutation_result}. LLM 回复: {summary_text[:100]}..."
        )
    return False


async def handle_summary_long_memory(
    plugin: "Mnemosyne",
    persona_id: str | None,
    session_id: str,
    memory_text: str,
    context_history: list[dict] | None = None,
) -> bool:
    """
    使用 LLM 总结短期对话历史形成长期记忆，并将其向量化后存入 Milvus。
    这是一个后台任务。
    """
    # logger = plugin.logger

    # --- 前置检查 ---
    if not await _check_summary_prerequisites(plugin, memory_text):
        return False

    try:
        # 1. 请求 LLM 进行总结
        llm_response = await _get_summary_llm_response(plugin, memory_text)
        if not llm_response:
            return False

        # 2. 提取总结文本
        summary_text = _extract_summary_text(plugin, llm_response)
        if not summary_text:
            return False

        # 3. 获取总结文本的 Embedding
        # 使用 AstrBot EmbeddingProvider（异步）
        try:
            if not plugin.embedding_provider:
                logger.error("Embedding Provider 不可用，无法获取总结的 Embedding")
                return False

            # 使用 AstrBot EmbeddingProvider 的 get_embedding 方法
            embedding_vector = await plugin.embedding_provider.get_embedding(
                summary_text
            )

            if not embedding_vector:
                logger.error(f"无法获取总结文本的 Embedding: '{summary_text[:100]}...'")
                return False

        except (ConnectionError, ValueError, RuntimeError) as e:
            logger.error(
                f"获取总结文本 Embedding 时出错: '{summary_text[:100]}...' - {e}",
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.error(
                f"获取总结文本 Embedding 时发生未知错误: '{summary_text[:100]}...' - {e}",
                exc_info=True,
            )
            return False

        metadata: dict[str, Any] = {}
        if plugin.config.get("use_participant_filtering", False) or plugin.config.get(
            "use_lightweight_memory_graph", True
        ):
            metadata = _build_lightweight_graph_metadata(summary_text, context_history)
        stored_content = pack_memory_content(summary_text, metadata)

        # 4. 存储到 Milvus
        return await _store_summary_to_milvus(
            plugin, persona_id, session_id, stored_content, embedding_vector
        )
    except Exception as e:
        logger.error(f"在总结或存储长期记忆的过程中发生严重错误: {e}", exc_info=True)
        return False


async def store_manual_memory(
    plugin: "Mnemosyne",
    event: AstrMessageEvent,
    memory_content: str,
    source: str = "manual",
    session_id: str | None = None,
    persona_id: str | None = None,
) -> bool:
    """
    直接写入一条长期记忆（不经过 LLM 总结），用于显式“记住”场景和手动命令。
    """
    normalized_content = (
        memory_content.strip() if isinstance(memory_content, str) else ""
    )
    if not normalized_content:
        logger.warning("手动记忆内容为空，已跳过。")
        return False

    if not await _check_summary_prerequisites(plugin, normalized_content):
        return False

    target_session_id = session_id or event.unified_msg_origin
    if not target_session_id or not validate_session_id(target_session_id):
        logger.error(f"手动记忆写入失败：无效 session_id={target_session_id}")
        return False

    target_persona = persona_id
    if not target_persona:
        target_persona = await _get_persona_id(plugin, event)

    if not plugin.embedding_provider:
        logger.error("手动记忆写入失败：Embedding Provider 不可用。")
        return False

    try:
        embedding_vector = await plugin.embedding_provider.get_embedding(
            normalized_content
        )
    except Exception as e:
        logger.error(f"手动记忆写入失败：获取 Embedding 异常: {e}", exc_info=True)
        return False

    if not embedding_vector:
        logger.error("手动记忆写入失败：Embedding 结果为空。")
        return False

    metadata = _build_lightweight_graph_metadata(
        normalized_content,
        context_history=[
            {
                "role": "user",
                "content": normalized_content,
                "metadata": {"speaker_id": str(event.get_sender_id())},
            }
        ],
    )
    metadata["source"] = source
    stored_content = pack_memory_content(normalized_content, metadata)

    return await _store_summary_to_milvus(
        plugin=plugin,
        persona_id=target_persona,
        session_id=target_session_id,
        summary_text=stored_content,
        embedding_vector=embedding_vector,
    )


# 计时器
async def _periodic_summarization_check(plugin: "Mnemosyne"):
    """
    [后台任务] 定期检查并触发超时的会话总结

    S0 优化: 添加异常恢复机制，防止任务崩溃
    """
    logger.info(
        f"启动定期总结检查任务，检查间隔: {plugin.summary_check_interval}秒, 总结时间阈值: {plugin.summary_time_threshold}秒。"
    )

    # S0 优化: 异常恢复计数器
    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            await asyncio.sleep(plugin.summary_check_interval)  # <--- 等待指定间隔

            if not plugin.context_manager or plugin.summary_time_threshold == float(
                "inf"
            ):
                # 如果上下文管理器未初始化或阈值无效，则跳过本次检查
                continue

            current_time = time.time()
            session_ids_to_check = list(plugin.context_manager.conversations.keys())

            # logger.debug(f"开始检查 {len(session_ids_to_check)} 个会话的总结超时...")

            for session_id in session_ids_to_check:
                try:
                    session_context = plugin.context_manager.get_session_context(
                        session_id
                    )
                    if not session_context:  # 会话可能在检查期间被移除
                        continue
                    # M24 修复: 添加 msg_counter 的类型检查
                    if (
                        not plugin.msg_counter
                        or plugin.msg_counter.get_counter(session_id) <= 0
                    ):
                        logger.debug(f"会话 {session_id} 没有新消息，跳过检查。")
                        continue

                    last_summary_time = session_context["last_summary_time"]

                    if current_time - last_summary_time > plugin.summary_time_threshold:
                        # logger.debug(f"current_time {current_time} - last_summary_time {last_summary_time} : {current_time - last_summary_time}")
                        logger.info(
                            f"会话 {session_id} 距离上次总结已超过阈值 ({plugin.summary_time_threshold}秒)，触发强制总结。"
                        )
                        # 运行总结
                        logger.info("开始总结历史对话...")
                        # M24 修复: 添加 msg_counter 的类型检查和类型忽略
                        counter = (
                            plugin.msg_counter.get_counter(session_id)
                            if plugin.msg_counter
                            else 0
                        )
                        history_contents = format_context_to_string(
                            session_context["history"],
                            counter,  # type: ignore
                        )
                        persona_id = await _get_persona_id(
                            plugin, session_context["event"]
                        )
                        asyncio.create_task(
                            handle_summary_long_memory(
                                plugin,
                                persona_id,
                                session_id,
                                history_contents,
                                context_history=session_context["history"],
                            )
                        )
                        logger.info("总结历史对话任务已提交到后台执行。")

                        # M24 修复: 添加 msg_counter 的类型检查
                        if plugin.msg_counter:
                            plugin.msg_counter.reset_counter(session_id)
                        plugin.context_manager.update_summary_time(session_id)

                except KeyError:
                    # 会话在获取 keys 后、处理前被删除，是正常情况
                    logger.debug(f"检查会话 {session_id} 时，会话已被移除。")
                except Exception as e:
                    logger.error(
                        f"检查或总结会话 {session_id} 时发生错误: {e}", exc_info=True
                    )

            # S0 优化: 成功完成一次循环，重置错误计数器
            consecutive_errors = 0

        except asyncio.CancelledError:
            logger.info("定期总结检查任务被取消。")
            break  # 退出循环
        except Exception as e:
            # S0 优化: 增强的异常处理和恢复机制
            consecutive_errors += 1
            logger.error(
                f"定期总结检查任务主循环发生错误 (连续错误次数: {consecutive_errors}/{max_consecutive_errors}): {e}",
                exc_info=True,
            )

            # 指数退避策略：等待时间随错误次数增加
            backoff_time = min(
                plugin.summary_check_interval * (2 ** (consecutive_errors - 1)), 300
            )
            logger.warning(f"将在 {backoff_time} 秒后重试后台总结任务...")

            try:
                await asyncio.sleep(backoff_time)
            except asyncio.CancelledError:
                logger.info("等待重试期间任务被取消。")
                break

            # 如果连续错误次数过多，记录严重警告但继续尝试
            if consecutive_errors >= max_consecutive_errors:
                logger.critical(
                    f"后台总结任务已连续失败 {consecutive_errors} 次，系统将继续尝试但可能存在严重问题，请检查日志并考虑重启插件。"
                )
                # 重置计数器以避免无限增长
                consecutive_errors = max_consecutive_errors - 1
