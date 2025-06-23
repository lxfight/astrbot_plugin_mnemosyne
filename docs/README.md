# 📚 Mnemosyne 文档中心 | Documentation Center

欢迎来到 Mnemosyne 插件的文档中心！这里包含了所有相关的使用指南、迁移文档和开发资源。  
Welcome to the Mnemosyne plugin documentation center! Here you'll find all relevant usage guides, migration documentation, and development resources.

---

## 📖 用户指南 | User Guides

### 🚀 快速开始 | Quick Start
- **[主页 README](../README.md)** - 插件概览和快速开始 | Plugin overview and quick start
- **[English README](../README_EN.md)** - English version of the main README
- **[快速入门 Wiki](https://github.com/lxfight/astrbot_plugin_mnemosyne/wiki/%E5%A6%82%E4%BD%95%E6%AD%A3%E7%A1%AE%E4%B8%94%E5%BF%AB%E9%80%9F%E7%9A%84%E9%A3%9F%E7%94%A8%E6%9C%AC%E6%8F%92%E4%BB%B6)** - 详细的快速入门指南 | Detailed quick start guide

### 📁 数据管理 | Data Management
- **[插件数据目录说明](guides/PLUGIN_DATA_DIRECTORY.md)** - 插件数据目录的使用和管理 | Plugin data directory usage and management

### 🗄️ 数据库教程 | Database Tutorials
- **[Milvus 使用教程](course_Milvus.md)** - Milvus 数据库的安装和使用 | Milvus database installation and usage

---

## 🔄 迁移文档 | Migration Documentation

### 📋 重构指南 | Refactoring Guide
- **[重构指南](migration/REFACTOR_GUIDE.md)** - v0.6.0 重构的详细说明 | Detailed explanation of v0.6.0 refactoring
- **[迁移示例](migration/MIGRATION_EXAMPLES.md)** - 具体的迁移使用示例 | Specific migration usage examples
- **[FAISS 配置更新](migration/FAISS_CONFIG_UPDATE.md)** - FAISS 配置结构更新指南 | FAISS configuration structure update guide

### 🔧 迁移工具 | Migration Tools
- **命令行迁移** | Command-line Migration:
  - `/memory status` - 查看当前状态 | Check current status
  - `/memory migrate_config` - 迁移配置 | Migrate configuration
  - `/memory migrate_to_faiss` - 迁移到 FAISS | Migrate to FAISS
  - `/memory migrate_to_milvus` - 迁移到 Milvus | Migrate to Milvus
  - `/memory validate_config` - 验证配置 | Validate configuration

---

## 🛠️ 开发文档 | Development Documentation

### 🧪 测试工具 | Testing Tools
- **[插件数据目录测试](development/test_plugin_data_path.py)** - 测试插件数据目录功能 | Test plugin data directory functionality
- **[迁移工具脚本](development/migration_tool.py)** - 独立的迁移工具脚本 | Standalone migration tool script

### 🏗️ 架构文档 | Architecture Documentation
- **核心组件** | Core Components:
  - `memory_manager/` - 内存管理模块 | Memory management module
  - `core/` - 核心功能模块 | Core functionality module
  - `main.py` - 插件主文件 | Main plugin file

### 📊 配置架构 | Configuration Schema
- **[配置架构文件](../_conf_schema.json)** - 插件配置的 JSON Schema | JSON Schema for plugin configuration

---

## 📝 更新日志 | Update Logs

### 📜 版本历史 | Version History
- **[更新日志](update_log.md)** - 详细的版本更新记录 | Detailed version update records

### 🆕 最新更新 | Latest Updates
- **v0.6.0** - 重大重构，多数据库支持 | Major refactoring, multi-database support
- **v0.5.0** - 生态兼容性改进 | Ecosystem compatibility improvements
- **v0.4.x** - 自动总结功能 | Auto-summarization features

---

## 🎯 使用场景指南 | Use Case Guides

### 👤 个人用户 | Personal Users
**推荐配置** | Recommended Configuration:
```json
{
  "vector_database_type": "faiss",
  "faiss_config": {
    "faiss_data_path": "faiss_data",
    "faiss_index_type": "IndexFlatL2",
    "faiss_nlist": 100
  }
}
```

**优势** | Advantages:
- 简单部署，无需额外服务 | Simple deployment, no additional services needed
- 本地存储，隐私安全 | Local storage, privacy and security
- 高性能向量搜索 | High-performance vector search

### 🏢 企业用户 | Enterprise Users
**推荐配置** | Recommended Configuration:
```json
{
  "vector_database_type": "milvus",
  "address": "localhost:19530",
  "authentication": {
    "user": "username",
    "password": "password"
  }
}
```

**优势** | Advantages:
- 分布式部署支持 | Distributed deployment support
- 企业级可靠性 | Enterprise-grade reliability
- 水平扩展能力 | Horizontal scaling capabilities

### 🔬 开发者 | Developers
**开发环境设置** | Development Environment Setup:
1. 克隆仓库 | Clone repository
2. 安装依赖 | Install dependencies
3. 运行测试 | Run tests
4. 查看架构文档 | Review architecture documentation

---

## 🔗 相关链接 | Related Links

### 📦 项目资源 | Project Resources
- **[GitHub 仓库](https://github.com/lxfight/astrbot_plugin_mnemosyne)** - 主项目仓库 | Main project repository
- **[发布页面](https://github.com/lxfight/astrbot_plugin_mnemosyne/releases)** - 版本发布 | Version releases
- **[问题反馈](https://github.com/lxfight/astrbot_plugin_mnemosyne/issues)** - Bug 报告和功能请求 | Bug reports and feature requests

### 🤝 社区支持 | Community Support
- **[QQ 讨论群](https://qm.qq.com/cgi-bin/qm/qr?k=WdyqoP-AOEXqGAN08lOFfVSguF2EmBeO&jump_from=webapi&authKey=tPyfv90TVYSGVhbAhsAZCcSBotJuTTLf03wnn7/lQZPUkWfoQ/J8e9nkAipkOzwh)** - 实时讨论和支持 | Real-time discussion and support

### 🧩 生态插件 | Ecosystem Plugins
- **[堆肥桶插件](https://github.com/Rail1bc/astrbot_plugin_composting_bucket)** - DeepSeek API 优化 | DeepSeek API optimization
- **[嵌入适配器](https://github.com/TheAnyan/astrbot_plugin_embedding_adapter)** - 嵌入服务增强 | Embedding service enhancement

---

## 📞 获取帮助 | Getting Help

### 🆘 常见问题 | Common Issues
1. **配置问题** | Configuration Issues: 查看 [迁移示例](migration/MIGRATION_EXAMPLES.md)
2. **数据库连接** | Database Connection: 参考 [Milvus 教程](course_Milvus.md)
3. **路径问题** | Path Issues: 阅读 [数据目录说明](guides/PLUGIN_DATA_DIRECTORY.md)

### 🔧 故障排除 | Troubleshooting
1. 使用 `/memory status` 检查状态 | Use `/memory status` to check status
2. 使用 `/memory validate_config` 验证配置 | Use `/memory validate_config` to validate configuration
3. 查看 AstrBot 日志获取详细错误信息 | Check AstrBot logs for detailed error information
4. 在 GitHub Issues 寻求帮助 | Seek help in GitHub Issues

---

## 🎉 贡献指南 | Contributing Guide

欢迎贡献代码、文档或反馈！  
Contributions of code, documentation, or feedback are welcome!

1. **Fork 项目** | Fork the project
2. **创建功能分支** | Create a feature branch
3. **提交更改** | Commit your changes
4. **推送到分支** | Push to the branch
5. **创建 Pull Request** | Create a Pull Request

---

*最后更新 | Last Updated: 2024-06-23*  
*文档版本 | Documentation Version: v0.6.0*
