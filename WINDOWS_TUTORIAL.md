# Windows 部署教程

本教程面向在 Windows 10/11 上运行 AstrBot 的用户。推荐使用默认的 Chroma 本地持久化模式，不需要安装 Docker 或额外的数据库服务。

## 前置条件

- AstrBot `v4.29.0` 至 `v4.x`
- Python `3.12+`
- 已在 AstrBot 中配置 LLM Provider 与 Embedding Provider
- 已安装 `uv`

## 方案选择

| 方案 | 适用场景 | 说明 |
| --- | --- | --- |
| Chroma | 个人使用、快速试用 | 默认后端，本地持久化，无需额外服务 |
| Milvus Standalone | 大规模数据、已有 Milvus 集群 | 通过 Docker 或独立服务部署 |
| Qdrant / Weaviate | 需要特定检索能力或已有服务 | 按需安装可选依赖 |

Milvus Lite 不支持 Windows，不建议在 Windows 上启用。需要 Milvus 时请使用 Docker Desktop 部署 Standalone。

## 1. 安装插件

可以通过 AstrBot 插件市场安装，也可以手动放入插件目录：

```powershell
cd D:\AstrBot\data\plugins
git clone https://github.com/lxfight/astrbot_plugin_mnemosyne.git astrbot_plugin_mnemosyne
```

在 AstrBot 根目录安装依赖：

```powershell
cd D:\AstrBot
uv pip install --python .venv\Scripts\python.exe -r data\plugins\astrbot_plugin_mnemosyne\requirements.txt
```

默认安装 Chroma。只有在切换到 Milvus、Qdrant 或 Weaviate 时才需要安装对应可选依赖。

## 2. 配置插件

启动 AstrBot 后打开 Dashboard（默认地址通常为 `http://127.0.0.1:6185`），进入 **插件管理 → Mnemosyne**：

1. 将 **向量数据库类型** 保持为 `chroma`。
2. 选择用于记忆总结的 LLM Provider。
3. 选择 Embedding Provider。
4. 保持集合名称为 `default`，或填写自定义名称。
5. 按需调整：
   - `num_pairs`: `5`，每 5 轮问答自动总结。
   - `top_k`: `3`，每次检索返回 3 条记忆。
   - `memory_injection_method`: `extra_user_parts`。

首次安装必须先初始化集合，否则记忆无法正常写入或检索。

## 3. 初始化与验证

重启或重载插件后，在聊天中由管理员执行：

```text
/memory init
```

然后进行至少 5 轮对话，观察日志中的 Mnemosyne 总结与写入信息。也可以手动验证：

```text
/memory remember 我的项目文档放在 D:\Projects\docs。
```

询问相关内容时，机器人应能检索并注入这条记忆。

## 4. 打开管理面板

1. 使用管理员账号登录 AstrBot Dashboard。
2. 进入 **Alkaid → 长期记忆**。
3. 查看系统状态、记忆列表、统计和会话分布。

管理视图不单独监听 `8000` 端口，也不使用独立 API Key。它运行在 AstrBot Dashboard 内，并继承管理员鉴权。

## 可选：切换到 Milvus Standalone

1. 安装 Docker Desktop 并启动 Milvus Standalone。
2. 在 AstrBot 的虚拟环境中安装 PyMilvus：

```powershell
cd D:\AstrBot
uv pip install --python .venv\Scripts\python.exe 'pymilvus>=2.6.0,<3.0.0'
```

3. 在插件配置中设置：

```json
{
  "vector_db_type": "milvus",
  "address": "127.0.0.1:19530",
  "db_name": "default"
}
```

4. 重启插件并执行 `/memory init --force`。

不同向量数据库之间不会自动迁移数据。切换前请备份旧数据库目录，并确认新后端已成功连接。

## 常见问题

### 提示 `chromadb 库未安装`

确认依赖安装到了 AstrBot 实际使用的虚拟环境：

```powershell
uv pip install --python D:\AstrBot\.venv\Scripts\python.exe -r D:\AstrBot\data\plugins\astrbot_plugin_mnemosyne\requirements.txt
```

### 记忆没有自动总结

- 检查对话是否达到 `num_pairs`。
- 检查 LLM Provider 和 Embedding Provider 是否可用。
- 检查平台是否在 `platform_blacklist` 中。
- 查看 AstrBot 日志中的 Mnemosyne 报错。

### 检索不到相关记忆

- 提高 `top_k` 后重试。
- 检查 `use_session_filtering`、`use_personality_filtering` 和 `use_participant_filtering`。
- 更换 Embedding 模型后执行 `/memory init --force`。
- 如不需要轻量图谱重排，可关闭 `use_lightweight_memory_graph` 后比较延迟与召回效果。

### Dashboard 中找不到管理视图

- 确认插件已成功加载且 AstrBot 版本不低于 `v4.29.0`。
- 确认当前账号具有管理员权限。
- 查看 AstrBot 日志中插件视图注册是否报错。

## 性能建议

- Chroma 本地模式适合个人和小规模部署，优先保证简单可靠。
- 增大 `num_pairs` 可减少总结调用，但记忆更新会更慢。
- 降低 `top_k` 可减少检索与上下文开销。
- 增大 `memory_injection_interval` 可降低记忆注入频率。
- 出现检索干扰时，优先检查过滤配置和图谱重排，而不是仅提高返回数量。

更多说明见[在线文档](https://lxfight.github.io/astrbot_plugin_mnemosyne/)。
