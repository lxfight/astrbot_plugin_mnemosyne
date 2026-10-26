# 故障排查

## 找不到 Embedding Provider

检查 AstrBot 的服务商配置，确保至少有一个 Embedding Provider 可用。插件需要 Embedding Provider 将文本转成向量。

## 记忆没有被总结

常见原因：

- 对话轮数没有达到 `num_pairs`。
- LLM Provider 未配置或请求失败。
- 平台命中了 `platform_blacklist`。
- 当前会话没有产生可总结的有效消息。

可以临时降低 `num_pairs`，然后观察 AstrBot 日志中的 Mnemosyne 信息。

## 检索不到相关记忆

检查以下配置：

- `top_k` 是否过低。
- `use_lightweight_memory_graph` 是否适合当前数据的实体分布。
- `use_session_filtering` 是否导致只检索当前会话。
- `use_personality_filtering` 是否过滤了当前人格之外的记忆。
- 是否更换过 Embedding 模型但没有重新初始化集合。

## Chroma 数据目录在哪里

如果 `chroma_config.persist_directory` 留空，插件会在默认数据目录中创建 Chroma 持久化目录。需要迁移机器时，先停止 AstrBot，再复制该目录。

## Milvus 连接失败

检查 `address`、`db_name` 和认证配置。使用标准 Milvus 时确认服务端口可访问：

```bash
nc -vz localhost 19530
```

如果使用 Milvus Lite，确认 `milvus_lite_path` 指向可写路径。

如果日志包含 `No module named 'pkg_resources'`，说明安装了依赖旧 setuptools 行为的 Milvus Lite。不要降级 AstrBot 的 setuptools；请升级可选依赖：

```bash
uv pip install --upgrade 'pymilvus[milvus_lite]>=2.6.0,<3.0.0'
```

新建 Milvus 集合的 `session_id` 字段长度为 500。对于旧的标准 Milvus 集合，插件会在启动时尝试从 72 在线扩容到 500；若服务器不支持，请升级 PyMilvus 与 Milvus 后重载插件。Milvus Lite 目前不支持在线修改字段，需改用新的集合名，或先导出旧集合再迁移到新集合。插件不会自动删除或重建已有集合。

## 切换数据库后旧记忆消失

不同数据库后端之间不会自动共享数据。切换数据库后，需要重新初始化并重新积累记忆，或自行编写迁移脚本导出旧记录再写入新后端。
