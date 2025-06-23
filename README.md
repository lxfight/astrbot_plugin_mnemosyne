# 🧠 Mnemosyne - Long-term Memory Hub for AstrBot

[中文](README.md) | [English](README_EN.md)

> *"Memory is the process of retaining information over time."*  
> *"Memory is the means by which we draw on our past experiences in order to use this information in the present."*
>
> **让 AI 真正记住与你的每一次对话，构建持久的个性化体验。**  
> **Enable AI to truly remember every conversation with you, building a persistent personalized experience.**

[![GitHub release](https://img.shields.io/github/v/release/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/releases)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/github/license/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/stargazers)

---

## 💬 支持与讨论 | Support & Discussion

遇到问题或想交流使用心得？加入我们的讨论群：  
Having issues or want to share experiences? Join our discussion group:

[![加入QQ群](https://img.shields.io/badge/QQ群-953245617-blue?style=flat-square&logo=tencent-qq)](https://qm.qq.com/cgi-bin/qm/qr?k=WdyqoP-AOEXqGAN08lOFfVSguF2EmBeO&jump_from=webapi&authKey=tPyfv90TVYSGVhbAhsAZCcSBotJuTTLf03wnn7/lQZPUkWfoQ/J8e9nkAipkOzwh)

在这里，你可以直接与开发者和其他用户交流，获取更及时的帮助。  
Here you can communicate directly with developers and other users for timely assistance.

---

## ✨ 功能特性 | Features

### 🧠 核心功能 | Core Features
- **🔄 多数据库支持** | Multi-Database Support: 支持 Milvus 和 FAISS 向量数据库
- **🤖 原生集成** | Native Integration: 深度集成 AstrBot 原生嵌入服务
- **📁 数据管理** | Data Management: 插件专属数据目录，自动路径管理
- **🔧 一键迁移** | One-Click Migration: 通过命令直接进行配置和数据迁移
- **⚡ 高性能** | High Performance: FAISS 本地高性能向量搜索
- **🔒 向后兼容** | Backward Compatible: 完全兼容旧版本配置

### 🆕 v0.6.0 新功能 | New in v0.6.0
- **🏗️ 现代化架构** | Modern Architecture: 重构插件架构，采用工厂模式和适配器模式
- **📊 统一接口** | Unified Interface: 统一的向量数据库和嵌入服务接口
- **🛠️ 迁移工具** | Migration Tools: 内置配置和数据迁移命令
- **📝 完善文档** | Complete Documentation: 详细的使用指南和最佳实践

---

## 🚀 快速开始 | Quick Start

### 📦 安装 | Installation

1. **下载插件** | Download Plugin
   ```bash
   # 克隆仓库 | Clone repository
   git clone https://github.com/lxfight/astrbot_plugin_mnemosyne.git
   
   # 或下载最新版本 | Or download latest release
   # https://github.com/lxfight/astrbot_plugin_mnemosyne/releases
   ```

2. **安装依赖** | Install Dependencies
   ```bash
   pip install -r requirements.txt
   ```

### ⚙️ 配置 | Configuration

#### 新用户推荐配置 | Recommended for New Users (FAISS)
```json
{
  "vector_database_type": "faiss",
  "faiss_config": {
    "faiss_data_path": "faiss_data",
    "faiss_index_type": "IndexFlatL2",
    "faiss_nlist": 100
  },
  "embedding_provider_id": "your_embedding_provider_id",
  "LLM_providers": "your_llm_provider_id"
}
```

#### 企业用户配置 | Enterprise Configuration (Milvus)
```json
{
  "vector_database_type": "milvus",
  "milvus_lite_path": "milvus.db",
  "embedding_provider_id": "your_embedding_provider_id",
  "LLM_providers": "your_llm_provider_id"
}
```

### 🔧 迁移命令 | Migration Commands

```bash
# 查看状态 | Check status
/memory status

# 迁移配置 | Migrate configuration
/memory migrate_config

# 迁移到 FAISS | Migrate to FAISS
/memory migrate_to_faiss --confirm

# 验证配置 | Validate configuration
/memory validate_config

# 获取帮助 | Get help
/memory help
```

---

## 📚 文档 | Documentation

### 📖 用户指南 | User Guides
- **[快速入门指南](https://github.com/lxfight/astrbot_plugin_mnemosyne/wiki/%E5%A6%82%E4%BD%95%E6%AD%A3%E7%A1%AE%E4%B8%94%E5%BF%AB%E9%80%9F%E7%9A%84%E9%A3%9F%E7%94%A8%E6%9C%AC%E6%8F%92%E4%BB%B6)** | Quick Start Guide
- **[插件数据目录说明](docs/guides/PLUGIN_DATA_DIRECTORY.md)** | Plugin Data Directory Guide

### 🔄 迁移文档 | Migration Documentation
- **[重构指南](docs/migration/REFACTOR_GUIDE.md)** | Refactoring Guide
- **[迁移示例](docs/migration/MIGRATION_EXAMPLES.md)** | Migration Examples

### 🛠️ 开发文档 | Development Documentation
- **[开发工具](docs/development/)** | Development Tools
- **[更新日志](docs/update_log.md)** | Update Log
- **[Milvus 教程](docs/course_Milvus.md)** | Milvus Tutorial

---

## 🎯 使用场景 | Use Cases

### 👤 个人用户 | Personal Users
- **简单部署**: 使用 FAISS 数据库，无需额外服务
- **本地存储**: 数据完全本地化，隐私安全
- **快速响应**: 高性能向量搜索，毫秒级响应

### 🏢 企业用户 | Enterprise Users  
- **分布式部署**: 使用 Milvus 支持大规模数据
- **高可用性**: 企业级数据库保障
- **可扩展性**: 支持集群部署和水平扩展

### 🔬 开发者 | Developers
- **模块化设计**: 清晰的架构便于二次开发
- **统一接口**: 易于扩展新的数据库后端
- **完整测试**: 提供测试工具和示例代码

---

## 🎉 更新日志 | Changelog

### 🚀 v0.6.0 (最新版本 | Latest)

**🏗️ 重大重构 | Major Refactoring**
- **多数据库支持** | Multi-Database Support: 新增 FAISS 数据库支持，与 Milvus 并存
- **原生集成** | Native Integration: 深度集成 AstrBot 原生嵌入服务系统
- **现代化架构** | Modern Architecture: 采用工厂模式和适配器模式重构
- **插件数据目录** | Plugin Data Directory: 使用 AstrBot 插件专属数据目录
- **一键迁移** | One-Click Migration: 通过命令直接进行配置和数据迁移

**🔧 新增命令 | New Commands**
- `/memory status` - 查看插件状态 | Check plugin status
- `/memory migrate_config` - 迁移配置 | Migrate configuration  
- `/memory migrate_to_faiss` - 迁移到 FAISS | Migrate to FAISS
- `/memory migrate_to_milvus` - 迁移到 Milvus | Migrate to Milvus
- `/memory validate_config` - 验证配置 | Validate configuration
- `/memory help` - 显示帮助 | Show help

### 🚀 v0.5.0

- **🔗 生态兼容** | Ecosystem Compatibility: 支持 [astrbot_plugin_embedding_adapter](https://github.com/TheAnyan/astrbot_plugin_embedding_adapter) 插件
- **⚡️ 优化修复** | Optimizations & Fixes: 多项内部优化和问题修复
- **⚖️ 协议更新** | License Update: 开源协议变更

<details>
<summary><strong>📜 历史版本 | Version History</strong></summary>

### 🚀 v0.4.1
- **🐛 Bug 修复** | Bug Fixes: 修复 Milvus 搜索结果处理问题
- **✨ 指令优化** | Command Optimization: 简化 `/memory list_records` 指令
- **✨ 模型支持** | Model Support: 新增 Google Gemini 嵌入模型支持

### 🚀 v0.4.0
- **✨ 自动总结** | Auto Summarization: 基于时间的自动总结功能
- **⚙️ 配置项** | Configuration: 新增计时器配置项
- **🛠️ 架构优化** | Architecture: 重构上下文管理器

### 🚀 v0.3.14
- **🐛 关键修复** | Critical Fix: 解决数据插入失败问题

### 🚀 v0.3.13
- **✨ Milvus Lite** | Milvus Lite: 新增本地轻量级数据库支持

</details>

---

## ⚠️ 重要提示 | Important Notes

### 🔄 从旧版本升级 | Upgrading from Old Versions

**v0.6.0 是重大更新，建议使用迁移工具：**  
**v0.6.0 is a major update, migration tools are recommended:**

1. **备份数据** | Backup Data: 升级前请备份重要数据
2. **使用迁移命令** | Use Migration Commands: 通过 `/memory migrate_config` 迁移配置
3. **验证配置** | Validate Configuration: 使用 `/memory validate_config` 验证
4. **查看文档** | Check Documentation: 参考 [迁移指南](docs/migration/REFACTOR_GUIDE.md)

### 📁 数据存储 | Data Storage

- **插件数据目录** | Plugin Data Directory: 所有数据存储在插件专属目录
- **相对路径支持** | Relative Path Support: 配置中的相对路径自动处理
- **数据隔离** | Data Isolation: 不同插件数据完全隔离

### 🔒 数据安全 | Data Security

> 🛡️ **数据安全提醒** | Data Security Reminder:  
> *"请像保护重要关系一样重视您的数据安全——毕竟，谁都不希望自己的数字伴侣突然'失忆'。"*  
> *"Protect your data like you protect important relationships - after all, no one wants their digital companion to suddenly 'lose memory'."*

---

## 🧩 插件生态 | Plugin Ecosystem

### 🚀 本插件优化 | This Plugin Optimizations
- **DeepSeek API 优化**: 集成 [@Rail1bc](https://github.com/Rail1bc) 的缓存优化代码
- **Token 节省**: 智能调整历史对话内容，提高缓存命中率

### ♻️ 推荐插件 | Recommended Plugins
- **[堆肥桶插件](https://github.com/Rail1bc/astrbot_plugin_composting_bucket)**: DeepSeek API 缓存优化
- **[嵌入适配器](https://github.com/TheAnyan/astrbot_plugin_embedding_adapter)**: 增强嵌入效果

---

## 🙏 致谢 | Acknowledgments

- 感谢 **AstrBot 核心开发团队** 提供的强大平台 | Thanks to **AstrBot Core Team** for the powerful platform
- 感谢 **[@Rail1bc](https://github.com/Rail1bc)** 的 DeepSeek API 优化贡献 | Thanks to **[@Rail1bc](https://github.com/Rail1bc)** for DeepSeek API optimizations
- 感谢所有贡献者和用户的支持 | Thanks to all contributors and users for their support

**如果本项目对您有帮助，请点亮 Star ⭐！**  
**If this project helps you, please give it a Star ⭐!**

---

## 🌟 贡献者 | Contributors

[![GitHub Contributors](https://img.shields.io/github/contributors/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors)

<a href="https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=lxfight/astrbot_plugin_mnemosyne" alt="Contributor List" />
</a>

---

## ✨ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne)

_每一个 Star 都是我们前进的灯塔！感谢您的关注！_  
_Every Star is a beacon for our progress! Thank you for your attention!_
