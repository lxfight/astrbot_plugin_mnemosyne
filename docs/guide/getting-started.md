# 快速开始

本页面向第一次安装 Mnemosyne 的用户。默认配置已经改为 Chroma，本地持久化，不需要启动 Milvus、Qdrant 或 Weaviate 服务。

## 前置条件

- AstrBot v4.0.0 或更高版本
- Python 3.8 或更高版本
- 已在 AstrBot 中配置至少一个 LLM Provider
- 已在 AstrBot 中配置至少一个 Embedding Provider

## 安装依赖

进入插件目录安装依赖：

```bash
cd data/plugins/astrbot_plugin_mnemosyne
uv pip install -r requirements.txt
```

默认依赖包含 Chroma。Milvus、Qdrant、Weaviate 是可选后端，需要时再取消 `requirements.txt` 中对应依赖的注释。

## 配置插件

在 AstrBot WebUI 中打开插件配置：

1. 进入 **插件管理**。
2. 打开 **Mnemosyne**。
3. 保持 **向量数据库类型** 为 `chroma`。
4. 选择用于记忆总结的 LLM Provider。
5. 选择用于向量化的 Embedding Provider。
6. 按需调整总结轮数、检索数量和相似度阈值。

Chroma 的 `persist_directory` 可以留空。留空时，插件会在自身数据目录中创建默认持久化目录。

## 初始化

首次安装后，使用管理员账号执行：

```text
/memory init
```

当 Embedding 维度变更、集合结构需要重建或从旧版本迁移时，可以执行：

```text
/memory init --force
```

## 验证运行

与机器人持续对话，达到配置的总结轮数后，日志中应出现 Mnemosyne 的总结与写入信息。

也可以手动写入一条记忆：

```text
/memory remember 我喜欢在晚上整理项目文档。
```

随后询问相关内容，观察机器人是否能检索并注入长期记忆。

## 管理面板

打开 AstrBot Dashboard，进入 **Alkaid** 中的长期记忆页面，可以查看记忆列表、连接状态和基础统计。

## 下一步

- 阅读[配置说明](/guide/configuration)理解核心配置。
- 阅读[数据库选择](/guide/database)决定是否切换到 Milvus、Qdrant 或 Weaviate。
- 阅读[管理面板](/guide/admin-panel)熟悉检索、编辑和删除操作。
- 阅读[命令与管理](/guide/commands)学习日常维护命令。
- 阅读[架构与数据流](/reference/architecture)理解总结与检索链路。
