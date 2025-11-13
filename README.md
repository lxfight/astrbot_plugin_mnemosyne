<div align="center">

# Mnemosyne

### AstrBot 长期记忆插件

<p align="center">
  <i>为 AI 赋予持久记忆能力，构建个性化对话体验</i>
</p>

---

[![License](https://img.shields.io/badge/license-Custom-blue.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v2.0.0-green.svg)](https://github.com/lxfight/astrbot_plugin_mnemosyne)
[![QQ Group](https://img.shields.io/badge/QQ群-953245617-blue?style=flat-square&logo=tencent-qq)](https://qm.qq.com/cgi-bin/qm/qr?k=WdyqoP-AOEXqGAN08lOFfVSguF2EmBeO&jump_from=webapi&authKey=tPyfv90TVYSGVhbAhsAZCcSBotJuTTLf03wnn7/lQZPUkWfoQ/J8e9nkAipkOzwh)

</div>

---

## 概述

**Mnemosyne** 是一个为 AstrBot 设计的长期记忆管理插件，基于 RAG (检索增强生成) 技术和 Milvus 向量数据库实现。该插件能够自动总结对话内容，将其转换为向量存储，并在后续对话中智能检索相关记忆，使 AI 具备真正的长期记忆能力。

<table>
<tr>
<td width="50%">

### 核心特性

<ul>
<li><strong>自动记忆总结</strong><br/>根据对话轮数自动触发记忆总结与存储</li>
<li><strong>智能记忆检索</strong><br/>基于语义相似度检索最相关的历史记忆</li>
<li><strong>会话隔离</strong><br/>为不同会话维护独立的记忆上下文</li>
<li><strong>向量化存储</strong><br/>使用 Milvus 进行高效的向量存储与检索</li>
</ul>

</td>
<td width="50%">

### 管理功能

<ul>
<li><strong>Web 管理面板</strong><br/>可视化管理记忆数据，支持查询、统计</li>
<li><strong>命令行工具</strong><br/>提供丰富的命令行指令管理记忆</li>
<li><strong>灵活配置</strong><br/>支持多种记忆注入方式与检索策略</li>
<li><strong>数据安全</strong><br/>支持 API 密钥认证保护管理端点</li>
</ul>

</td>
</tr>
</table>

---

## 技术架构

<table>
<tr>
<th width="25%">组件</th>
<th width="75%">说明</th>
</tr>
<tr>
<td><strong>向量数据库</strong></td>
<td>基于 Milvus / Milvus Lite 进行向量存储与检索，支持多种索引类型</td>
</tr>
<tr>
<td><strong>Embedding 服务</strong></td>
<td>集成 AstrBot 的 Embedding Provider，自动获取文本向量表示</td>
</tr>
<tr>
<td><strong>LLM 总结</strong></td>
<td>使用配置的 LLM Provider 进行对话内容总结，生成结构化记忆</td>
</tr>
<tr>
<td><strong>上下文管理</strong></td>
<td>维护对话历史与记忆注入，支持多种注入策略（用户提示/系统提示）</td>
</tr>
<tr>
<td><strong>Web 管理面板</strong></td>
<td>基于 FastAPI 的管理界面，提供记忆查询、统计、监控功能</td>
</tr>
</table>

---

## 主要功能

### 记忆管理

- **自动总结机制**：根据配置的对话轮数阈值自动触发总结
- **时间触发总结**：支持基于时间阈值的定期总结（可选）
- **人格过滤**：支持按人格配置过滤记忆检索结果
- **会话过滤**：支持按会话隔离记忆，或禁用以实现全局记忆共享
- **多集合支持**：可为不同场景创建独立的记忆集合

### 命令系统

```
/memory init [--force]                    初始化/迁移记忆系统（管理员，首次安装必须）
/memory list                              查看所有记忆集合
/memory list_records [collection] [limit] 列出指定集合的记忆记录
/memory get_session_id                    获取当前会话 ID
/memory reset [confirm]                   清除当前会话记忆
/memory delete_session_memory [id] [confirm]  删除指定会话记忆（管理员）
/memory drop_collection [name] [confirm] 删除整个集合（管理员）
```

**重要命令说明：**

- `/memory init` - 首次安装后必须执行，用于创建正确维度的集合
- `/memory init --force` - 强制重新初始化，用于维度迁移（会保留数据）

### 配置选项

<table>
<tr>
<th>配置项</th>
<th>说明</th>
<th>默认值</th>
</tr>
<tr>
<td><code>num_pairs</code></td>
<td>触发总结的对话轮数阈值</td>
<td>5</td>
</tr>
<tr>
<td><code>top_k</code></td>
<td>检索返回的记忆数量</td>
<td>3</td>
</tr>
<tr>
<td><code>collection_name</code></td>
<td>Milvus 集合名称</td>
<td>default</td>
</tr>
<tr>
<td><code>memory_injection_method</code></td>
<td>记忆注入方式</td>
<td>user_prompt</td>
</tr>
<tr>
<td><code>use_personality_filtering</code></td>
<td>是否启用人格过滤</td>
<td>true</td>
</tr>
<tr>
<td><code>use_session_filtering</code></td>
<td>是否启用会话过滤。如果禁用，所有会话将共享记忆</td>
<td>true</td>
</tr>
</table>

### 会话过滤功能

插件支持灵活的会话记忆管理，通过 `use_session_filtering` 配置项控制：

#### 会话隔离模式（默认）
- **配置**：`use_session_filtering: true`
- **行为**：每个会话拥有独立的记忆空间
- **适用场景**：
  - 多用户环境，确保用户隐私
  - 不同对话主题需要独立上下文
  - 避免不同会话间的记忆干扰

#### 全局记忆模式
- **配置**：`use_session_filtering: false`
- **行为**：所有会话共享同一个记忆池
- **适用场景**：
  - 单用户环境，希望AI记住所有对话历史
  - 需要跨会话的知识积累
  - 构建全局知识库

**注意**：无论使用哪种模式，记忆在存储时都会保留原始的 `session_id`，确保可以随时切换模式而不丢失数据。

---

## 快速开始

### 先决条件

- AstrBot v4.0.0+
- Python 3.8+
- Milvus 数据库（可选择 Milvus Lite 或 Standalone）
- **⚠️ 必须先配置 Embedding Provider**

### 安装步骤

<table>
<tr>
<td width="5%"><strong>1</strong></td>
<td>

**安装依赖**
```bash
cd data/plugins/astrbot_plugin_mnemosyne
uv pip install -r requirements.txt
```

</td>
</tr>
<tr>
<td><strong>2</strong></td>
<td>

**配置 Milvus**

选择以下方式之一：

- **Milvus Lite**（轻量级，无需额外服务，不支持windows系统）
  ```json
  {
    "milvus_lite_path": "./data/milvus.db"
  }
  ```

- **Milvus Standalone**（完整功能）
  ```json
  {
    "address": "127.0.0.1:19530"
  }
  ```

</td>
</tr>
<tr>
<td><strong>3</strong></td>
<td>

**⚠️ 配置 Embedding Provider（必须）**

在 AstrBot WebUI 中**必须先配置** Embedding Provider，插件需要使用其向量维度来创建集合。

支持的 Embedding Provider：
- OpenAI Embedding
- Gemini Embedding
- 其他兼容的 Embedding 服务

</td>
</tr>
<tr>
<td><strong>4</strong></td>
<td>

**配置插件**

在 AstrBot WebUI 中进行插件配置，设置：
- LLM Provider（用于记忆总结）
- 记忆管理参数（如 num_pairs、top_k 等）

</td>
</tr>
<tr>
<td><strong>5</strong></td>
<td>

**初始化记忆系统**

启动 AstrBot 后，执行以下命令初始化记忆系统：

```
/memory init
```

这将：
- 检测 Embedding Provider 的向量维度
- 创建匹配维度的 Milvus 集合
- 建立必要的索引

**首次安装必须执行此命令！**

</td>
</tr>
</table>

### 🔄 维度迁移（老用户）

如果您更换了 Embedding Provider 或模型，导致向量维度变化，系统会自动检测并提示您迁移数据：

1. 执行 `/memory init` 检查维度
2. 如果维度不匹配，系统会提示需要迁移
3. 执行 `/memory init --force` 确认迁移

**迁移过程：**
- ✅ 自动备份文本内容
- ✅ 使用新维度重新生成向量
- ✅ 保留所有历史记忆数据
- ⚠️ 迁移过程可能需要一些时间，取决于记忆数量

详细的部署指南请参阅：**[快速启动指南 (QUICKSTART.md)](./QUICKSTART.md)**

或访问 Wiki：**[如何正确且快速地食用本插件](https://github.com/lxfight/astrbot_plugin_mnemosyne/wiki/%E5%A6%82%E4%BD%95%E6%AD%A3%E7%A1%AE%E4%B8%94%E5%BF%AB%E9%80%9F%E7%9A%84%E9%A3%9F%E7%94%A8%E6%9C%AC%E6%8F%92%E4%BB%B6)**

---

## Web 管理面板

插件内置了基于 FastAPI 的管理面板，提供以下功能：

- 记忆数据查询与浏览
- 会话统计与分析
- 实时监控与日志查看
- 记忆数据导出

**访问地址**：`http://127.0.0.1:8000`（默认端口）

**安全配置**：
- 支持 API 密钥认证
- 可在配置文件中设置固定密钥
- 未配置时自动生成临时密钥（每次重启变化）

---

## 技术细节

### 记忆存储流程

```
对话消息 → 达到轮数阈值 → LLM 总结 → Embedding 向量化 → Milvus 存储
```

### 记忆检索流程

```
用户输入 → Embedding 向量化 → Milvus 相似度检索 → 过滤筛选 → 注入上下文
```

### 数据模型

每条记忆记录包含以下字段：
- `id`：唯一标识符
- `text`：总结后的文本内容
- `embedding`：文本的向量表示
- `session_id`：关联的会话 ID
- `persona_id`：关联的人格 ID
- `timestamp`：创建时间戳
- `metadata`：扩展元数据

---

## 许可证

本项目采用自定义许可证，详见 [LICENSE](./LICENSE) 文件。

---

## 支持与反馈

<table>
<tr>
<td width="50%">

### 问题报告

如遇到 Bug 或功能问题，请在 GitHub Issues 中提交问题报告。

[提交 Issue →](https://github.com/lxfight/astrbot_plugin_mnemosyne/issues)

</td>
<td width="50%">

### 社区讨论

加入 QQ 群与开发者和用户交流：

**群号：953245617**

[点击加入 →](https://qm.qq.com/cgi-bin/qm/qr?k=WdyqoP-AOEXqGAN08lOFfVSguF2EmBeO&jump_from=webapi&authKey=tPyfv90TVYSGVhbAhsAZCcSBotJuTTLf03wnn7/lQZPUkWfoQ/J8e9nkAipkOzwh)

</td>
</tr>
</table>

### 贡献代码

欢迎提交 Pull Request 贡献代码或改进文档。

---

<div align="center">

**项目地址**：[github.com/lxfight/astrbot_plugin_mnemosyne](https://github.com/lxfight/astrbot_plugin_mnemosyne)

**作者**：lxfight | **版本**：v2.0.0

---

*让 AI 拥有真正的记忆*

</div>