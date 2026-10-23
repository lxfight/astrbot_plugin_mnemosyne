---
layout: home

hero:
  name: Mnemosyne
  text: AstrBot 长期记忆插件
  tagline: 为 AstrBot 提供可检索、可管理、可迁移的长期记忆能力。默认使用 Chroma，本地持久化，无需额外数据库服务。
  image:
    src: /mnemosyne-mark.svg
    alt: Mnemosyne
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/getting-started
    - theme: alt
      text: 数据库选择
      link: /guide/database

features:
  - title: 默认 Chroma
    details: 新安装默认使用本地 Chroma，安装依赖后即可启动，适合个人部署和快速试用。
  - title: 多数据库架构
    details: 统一适配 Chroma、Milvus、Qdrant、Weaviate，按部署规模切换后端。
  - title: AstrBot 原生集成
    details: 使用 AstrBot 的 LLM Provider 和 Embedding Provider，记忆总结、检索和注入都在插件内完成。
  - title: 会话与人格过滤
    details: 支持按会话、人格和参与者过滤记忆，减少多用户和群聊场景中的串线。
  - title: Web 管理面板
    details: 可在 AstrBot Dashboard 中查看、搜索、删除记忆记录，并观察数据库连接状态。
  - title: 命令化运维
    details: 提供初始化、记忆写入、记录删除、集合清理等管理命令。
---

## 文档入口

- 需要马上跑起来：阅读[快速开始](/guide/getting-started)。
- 需要理解配置项：阅读[配置说明](/guide/configuration)。
- 需要选择向量数据库：阅读[数据库选择](/guide/database)。
- 需要日常管理：阅读[管理面板](/guide/admin-panel)与[命令与管理](/guide/commands)。
- 需要理解实现：阅读[架构与数据流](/reference/architecture)。
- 需要参与开发：阅读[本地开发与文档部署](/reference/development)。

English documentation is available at [/en/](/en/).
