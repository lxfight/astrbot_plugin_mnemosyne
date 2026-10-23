# 配置说明

Mnemosyne 的配置分为模型服务、向量数据库、记忆策略和管理能力几类。最小可用配置只需要保留默认 Chroma，并选择 LLM 与 Embedding Provider。

## 模型服务

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `LLM_providers` | 用于总结对话的 LLM Provider。留空时使用当前会话默认 Provider。 | 空 |
| `embedding_provider_id` | 用于生成文本向量的 Embedding Provider。留空时使用 AstrBot 中第一个可用 Provider。 | 空 |

Embedding Provider 的向量维度决定集合结构。更换 Embedding 模型后，建议执行 `/memory init --force` 检查或重建集合。

## 向量数据库

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `vector_db_type` | 向量数据库类型，可选 `chroma`、`milvus`、`qdrant`、`weaviate`。 | `chroma` |
| `collection_name` | 存储长期记忆的集合名称。 | `default` |
| `chroma_config.persist_directory` | Chroma 本地持久化路径。留空时使用插件数据目录。 | 空 |
| `chroma_config.host` | Chroma HTTP 服务地址。留空时使用本地持久化模式。 | 空 |
| `qdrant_config.path` | Qdrant 本地持久化路径。 | 空 |
| `qdrant_config.url` | Qdrant 服务端地址。 | 空 |
| `weaviate_config.embedded` | 是否使用 Weaviate 嵌入式模式。 | `false` |
| `milvus_lite_path` | Milvus Lite 数据文件路径。 | 空 |
| `address` | 标准 Milvus 服务地址。 | 空 |
| `db_name` | Milvus 数据库名。 | `default` |

更多选择建议见[数据库选择](/guide/database)。

## 记忆策略

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `num_pairs` | 触发自动总结的对话轮数。 | `5` |
| `top_k` | 检索时返回的记忆数量。 | `3` |
| `contexts_memory_len` | 注入上下文的长期记忆数量。 | `3` |
| `memory_injection_method` | `user_prompt` 注入用户提示；`system_prompt` 注入 LLM 系统提示；`insert_system_prompt` 新增独立系统消息。 | `user_prompt` |
| `memory_injection_position` | 注入位置，可选前置或后置。 | `prepend` |
| `summary_fallback_provider_id` | 主总结模型失败或返回空内容时重试的备用模型。 | 空 |
| `summary_speaker_mapping_prompt` | 约束 `user`、`assistant` 和第一人称归属，支持会话与说话人变量。 | 内置通用映射 |
| `score_threshold` | 相似度阈值，低于阈值的记忆会被过滤。 | `0.0` |
| `enable_llm_memory_tool` | 允许支持工具调用的模型通过 `mnemosyne_remember_memory` 写入当前会话记忆。关闭后模型仍可调用工具，但不会写入。 | `true` |

如果记忆过多干扰回复，可以降低 `top_k`、提高 `score_threshold` 或减少 `contexts_memory_len`。

`memory_injection_position` 同时控制 `user_prompt` 和 `system_prompt` 的前后位置。`insert_system_prompt` 会创建独立系统消息；部分模型会因此重新计算提示词缓存，缓存成本敏感时优先使用前两种方式。

## 过滤能力

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `use_session_filtering` | 按会话隔离记忆。关闭后所有会话共享记忆池。 | `true` |
| `use_personality_filtering` | 按人格过滤记忆。 | `true` |
| `use_participant_filtering` | 在群聊中优先检索当前参与者相关记忆。 | `false` |
| `platform_blacklist` | 禁用长期记忆的平台 ID 列表。 | `[]` |

会话隔离适合多用户或群聊场景。全局记忆适合单用户助手或共享知识库场景。

## 轻量图谱重排

`use_lightweight_memory_graph` 启用后，插件会从记忆中抽取轻量实体关系，并在检索时做 one-hop 扩展与重排。这个功能适合长期积累关系型信息，例如人物偏好、项目上下文和跨会话线索。

如果更看重检索速度或希望先保持行为简单，可以关闭该选项。
