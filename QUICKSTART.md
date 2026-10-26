# 快速启动指南

本指南用于在 AstrBot 中完成 Mnemosyne 的最小可用部署。默认使用 Chroma 本地持久化，不需要额外启动数据库服务。

## 前置条件

- AstrBot `v4.29.0` 至 `v4.x`
- Python `3.12+`
- 已在 AstrBot 中配置 LLM Provider 与 Embedding Provider

## 1. 安装依赖

在 AstrBot 使用的虚拟环境中执行：

```bash
cd data/plugins/astrbot_plugin_mnemosyne
uv pip install -r requirements.txt
```

默认依赖包含 Chroma。Milvus、Qdrant 和 Weaviate 是可选后端，需要时再启用 `requirements.txt` 中对应依赖。

## 2. 配置插件

登录 AstrBot Dashboard，进入 **插件管理**，打开 **Mnemosyne**：

1. 保持 **向量数据库类型** 为 `chroma`。
2. 选择用于记忆总结的 LLM Provider。
3. 选择用于生成向量的 Embedding Provider。
4. 按需调整以下默认值：
   - `num_pairs`: `5`，每 5 轮问答触发一次自动总结。
   - `top_k`: `3`，每轮检索返回的记忆条数。
   - `memory_injection_method`: `extra_user_parts`，把记忆作为临时内容块追加到当前用户消息。

Embedding Provider 的向量维度决定集合结构。首次安装后必须先初始化集合，再开始积累记忆。

## 3. 初始化

重启或重载 AstrBot 后，使用管理员账号执行：

```text
/memory init
```

更换 Embedding 模型、维度变化或需要重建集合时执行：

```text
/memory init --force
```

`--force` 会重建集合并重新生成历史记忆的向量。数据量大时应预留足够时间，并先备份数据库目录。

## 4. 验证

1. 与机器人持续对话，达到 `num_pairs` 后观察日志中的总结和写入记录。
2. 手动写入一条记忆：

```text
/memory remember 我喜欢在晚上整理项目文档。
```

3. 询问相关内容，确认检索结果被注入当前对话。

## 管理面板

登录 AstrBot Dashboard，进入 **Alkaid → 长期记忆**。管理视图不单独监听端口，不维护独立 API Key，权限继承 Dashboard 管理员会话。

## 常见问题

### 找不到 Embedding Provider

在 AstrBot 的服务商配置中添加至少一个可用的 Embedding Provider，然后在插件配置中重新选择。

### 记忆没有被总结

检查对话是否达到 `num_pairs`、LLM Provider 是否可用、平台是否命中 `platform_blacklist`。

### 检索不到相关记忆

- 适当提高 `top_k`。
- 检查 `use_session_filtering` 与 `use_personality_filtering` 是否过滤了目标记忆。
- 更换 Embedding 模型后执行 `/memory init --force`。
- 检查 `use_lightweight_memory_graph` 是否适合当前数据。

### 如何清理长期记忆

AstrBot 的 `/new` 和 `/reset` 只处理短期会话。清理当前会话的长期记忆请使用：

```text
/memory reset confirm
```

## 性能建议

- 增大 `num_pairs` 可以减少总结调用，但会降低记忆更新频率。
- 降低 `top_k` 可以减少嵌入和上下文开销，但可能降低召回率。
- 增大 `memory_injection_interval` 可以降低注入频率。
- `extra_user_parts` 不会写入会话历史，通常比修改系统提示词更适合缓存敏感场景。

完整配置、数据库选择与调优说明见[在线文档](https://lxfight.github.io/astrbot_plugin_mnemosyne/)。
