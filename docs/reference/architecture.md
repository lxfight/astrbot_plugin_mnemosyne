# 架构与数据流

Mnemosyne 把对话总结、向量化、检索和提示词注入放在同一个 AstrBot 插件进程内完成。默认后端是本地 Chroma，因此首次部署不需要额外数据库服务。

## 组件

| 组件 | 职责 |
| --- | --- |
| `main.py` | 注册插件、初始化 Provider、数据库、管理面板和消息处理入口。 |
| `memory_manager/context_manager.py` | 维护对话上下文和长期记忆注入位置。 |
| `memory_manager/message_counter.py` | 统计会话轮数，触发自动总结。 |
| `core/memory_operations.py` | 实现总结写入、向量检索、过滤、重排和注入。 |
| `memory_manager/vector_db/` | 为 Chroma、Milvus、Qdrant、Weaviate 提供统一适配接口。 |
| `admin_panel/` 与 `web_api.py` | 提供统计、检索、编辑、删除和运行状态 API。 |

## 写入链路

```text
对话消息
  -> 消息计数达到 num_pairs
  -> LLM 总结
  -> Embedding Provider 生成向量
  -> 向量数据库 insert
  -> flush（后端支持时）
```

总结任务在后台执行。写入成功后即使 flush 失败，记忆本身仍然有效，等待后端异步可见，不会触发重复写入。写入失败时，会话计数器会回滚，下一轮对话可以重新触发总结。

## 检索链路

```text
LLM 请求
  -> 检查 memory_injection_interval
  -> 用户查询 Embedding
  -> 向量数据库相似度搜索
  -> 会话/人格/参与者过滤与关键词、图谱重排
  -> 注入带数据边界提示的长期记忆
```

没有可重排关键词且未启用参与者过滤时，候选数直接等于 `top_k`；否则使用 `min(top_k * 4, 60)` 扩大候选集。检索结果最终只保留 `top_k` 条进入提示词。

注入内容会明确标记为历史背景数据而不是指令，降低记忆内容被模型误当作系统要求或工具调用的风险。

## 数据模型

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `memory_id` | INT64，自动主键 | 记忆记录 ID。 |
| `personality_id` | VARCHAR(256) | 关联的人格 ID。 |
| `session_id` | VARCHAR(500) | 关联会话，用于隔离或筛选。 |
| `content` | VARCHAR(4096) | 总结后的记忆正文。 |
| `embedding` | FLOAT_VECTOR | 由当前 Embedding Provider 生成的向量。 |
| `create_time` | INT64 | Unix 时间戳，用于时间筛选和展示。 |

向量维度由 Embedding 模型决定。更换模型后需要执行 `/memory init --force` 检查或重建集合。

## 后端抽象

所有后端都实现连接、集合初始化、插入、搜索、查询、删除和 flush 等通用操作。业务层不依赖具体数据库 SDK，因此切换后端只需修改配置并在新后端初始化集合。

不同后端之间不会自动迁移数据。跨后端迁移需要导出旧记录，重新生成 Embedding 后写入新集合。

## 可观测性

插件进程维护分阶段延迟和 API 成功率，管理面板读取同一份指标。慢查询阈值覆盖 Embedding、向量搜索、后处理、注入、数据库操作和完整检索链路，便于区分模型网络、数据库后端和本地 CPU 开销。
