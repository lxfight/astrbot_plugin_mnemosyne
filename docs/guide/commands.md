# 命令与管理

Mnemosyne 提供 `/memory` 命令用于初始化、查询、写入和清理长期记忆。部分破坏性命令需要管理员权限和确认参数。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `/memory init [--force]` | 初始化或迁移记忆系统。首次安装必须执行。 |
| `/memory list` | 查看所有记忆集合。 |
| `/memory list_records [collection] [limit]` | 列出指定集合中的记忆记录。 |
| `/memory get_session_id` | 获取当前会话 ID。 |
| `/memory remember [content]` | 手动写入一条长期记忆。 |
| `/memory reset [confirm]` | 清除当前会话记忆。 |
| `/memory delete_record [id] [session] [confirm]` | 删除指定会话中的单条记忆。 |
| `/memory delete_session_memory [id] [confirm]` | 删除指定会话的全部记忆。 |
| `/memory delete_before [time] [session] [--confirm]` | 预览或删除指定时间以前的记忆。 |
| `/memory delete_between [start] [end] [session] [--confirm]` | 预览或删除一个时间范围内的记忆。 |
| `/memory export [filename] [session\|--all] [start] [end]` | 导出记忆为 JSON 文件。 |
| `/memory import [filename] [--confirm]` | 预览或导入 Mnemosyne JSON 导出文件。 |
| `/memory stats [session\|--all]` | 查看记忆数量和时间范围统计。 |
| `/memory search [keyword] [session\|--all] [limit]` | 按关键词搜索记忆内容。 |
| `/memory drop_collection [name] [confirm]` | 删除整个集合。 |

## 初始化

首次安装、切换数据库或更换 Embedding 模型后，建议执行：

```text
/memory init
```

如果集合结构需要重建：

```text
/memory init --force
```

## 手动写入记忆

当 `enable_explicit_memory_capture` 开启时，可以通过自然语言触发记忆写入。也可以直接使用命令：

```text
/memory remember 用户正在调试 Mnemosyne 的 VitePress 文档站。
```

## 删除数据

删除命令通常需要确认参数。执行前先使用 `list_records` 或管理面板确认记录 ID。

```text
/memory delete_record 123456 current_session confirm
```

如果需要清空当前会话：

```text
/memory reset confirm
```

## 时间清理与导入导出

`delete_before` 和 `delete_between` 会先输出预览，只有追加 `--confirm` 才会删除。所有这类命令，以及导出、导入、统计和搜索命令，均只允许 AstrBot 管理员执行。

```text
/memory delete_before 2026-07-01
/memory delete_before 2026-07-01 --confirm
/memory delete_between 2026-06-01 2026-07-01 --confirm
```

未指定会话 ID 时，命令只处理当前会话；使用 `--all` 才会导出、统计或搜索全部会话。导出文件始终保存在插件数据目录的 `exports` 子目录，导入会重新生成 Embedding，且先预览再确认。

```text
/memory export july-memory.json
/memory export full-memory.json --all
/memory import july-memory.json
/memory import july-memory.json --confirm
/memory stats
/memory search 偏好
```

## Web 管理面板

在 AstrBot Dashboard 的 **Alkaid** 页面中打开长期记忆管理，可以完成以下操作：

- 查看数据库连接状态。
- 搜索和浏览记忆记录。
- 删除单条记录或会话记忆。
- 查看集合统计信息。

管理面板与命令系统共用同一套数据库接口，因此 Chroma、Milvus、Qdrant 和 Weaviate 都可以使用相同的管理入口。
