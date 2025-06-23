# 🧠 Mnemosyne - Long-term Memory Hub for AstrBot

[中文](README.md) | [English](README_EN.md)

> *"Memory is the process of retaining information over time."*  
> *"Memory is the means by which we draw on our past experiences in order to use this information in the present."*
>
> **Enable AI to truly remember every conversation with you, building a persistent personalized experience.**

[![GitHub release](https://img.shields.io/github/v/release/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/releases)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/github/license/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/stargazers)

---

## 💬 Support & Discussion

Having issues or want to share experiences? Join our discussion group:

[![Join QQ Group](https://img.shields.io/badge/QQ群-953245617-blue?style=flat-square&logo=tencent-qq)](https://qm.qq.com/cgi-bin/qm/qr?k=WdyqoP-AOEXqGAN08lOFfVSguF2EmBeO&jump_from=webapi&authKey=tPyfv90TVYSGVhbAhsAZCcSBotJuTTLf03wnn7/lQZPUkWfoQ/J8e9nkAipkOzwh)

Here you can communicate directly with developers and other users for timely assistance.

---

## ✨ Features

### 🧠 Core Features
- **🔄 Multi-Database Support**: Support for both Milvus and FAISS vector databases
- **🤖 Native Integration**: Deep integration with AstrBot's native embedding services
- **📁 Data Management**: Plugin-specific data directory with automatic path management
- **🔧 One-Click Migration**: Direct configuration and data migration through commands
- **⚡ High Performance**: FAISS local high-performance vector search
- **🔒 Backward Compatible**: Fully compatible with legacy configurations

### 🆕 New in v0.6.0
- **🏗️ Modern Architecture**: Refactored plugin architecture using factory and adapter patterns
- **📊 Unified Interface**: Unified vector database and embedding service interfaces
- **🛠️ Migration Tools**: Built-in configuration and data migration commands
- **📝 Complete Documentation**: Detailed usage guides and best practices

---

## 🚀 Quick Start

### 📦 Installation

1. **Download Plugin**
   ```bash
   # Clone repository
   git clone https://github.com/lxfight/astrbot_plugin_mnemosyne.git
   
   # Or download latest release
   # https://github.com/lxfight/astrbot_plugin_mnemosyne/releases
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### ⚙️ Configuration

#### Recommended for New Users (FAISS)
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

#### Enterprise Configuration (Milvus)
```json
{
  "vector_database_type": "milvus",
  "milvus_lite_path": "milvus.db",
  "embedding_provider_id": "your_embedding_provider_id",
  "LLM_providers": "your_llm_provider_id"
}
```

### 🔧 Migration Commands

```bash
# Check status
/memory status

# Migrate configuration
/memory migrate_config

# Migrate to FAISS
/memory migrate_to_faiss --confirm

# Validate configuration
/memory validate_config

# Get help
/memory help
```

---

## 📚 Documentation

### 📖 User Guides
- **[Quick Start Guide](https://github.com/lxfight/astrbot_plugin_mnemosyne/wiki/%E5%A6%82%E4%BD%95%E6%AD%A3%E7%A1%AE%E4%B8%94%E5%BF%AB%E9%80%9F%E7%9A%84%E9%A3%9F%E7%94%A8%E6%9C%AC%E6%8F%92%E4%BB%B6)**
- **[Plugin Data Directory Guide](docs/guides/PLUGIN_DATA_DIRECTORY.md)**

### 🔄 Migration Documentation
- **[Refactoring Guide](docs/migration/REFACTOR_GUIDE.md)**
- **[Migration Examples](docs/migration/MIGRATION_EXAMPLES.md)**

### 🛠️ Development Documentation
- **[Development Tools](docs/development/)**
- **[Update Log](docs/update_log.md)**
- **[Milvus Tutorial](docs/course_Milvus.md)**

---

## 🎯 Use Cases

### 👤 Personal Users
- **Simple Deployment**: Use FAISS database without additional services
- **Local Storage**: Completely localized data for privacy and security
- **Fast Response**: High-performance vector search with millisecond response

### 🏢 Enterprise Users  
- **Distributed Deployment**: Use Milvus for large-scale data support
- **High Availability**: Enterprise-grade database guarantees
- **Scalability**: Support for cluster deployment and horizontal scaling

### 🔬 Developers
- **Modular Design**: Clear architecture for easy secondary development
- **Unified Interface**: Easy to extend new database backends
- **Complete Testing**: Provides testing tools and example code

---

## 🎉 Changelog

### 🚀 v0.6.0 (Latest)

**🏗️ Major Refactoring**
- **Multi-Database Support**: Added FAISS database support alongside Milvus
- **Native Integration**: Deep integration with AstrBot's native embedding service system
- **Modern Architecture**: Refactored using factory and adapter patterns
- **Plugin Data Directory**: Uses AstrBot's plugin-specific data directory
- **One-Click Migration**: Direct configuration and data migration through commands

**🔧 New Commands**
- `/memory status` - Check plugin status
- `/memory migrate_config` - Migrate configuration  
- `/memory migrate_to_faiss` - Migrate to FAISS
- `/memory migrate_to_milvus` - Migrate to Milvus
- `/memory validate_config` - Validate configuration
- `/memory help` - Show help

### 🚀 v0.5.0

- **🔗 Ecosystem Compatibility**: Support for [astrbot_plugin_embedding_adapter](https://github.com/TheAnyan/astrbot_plugin_embedding_adapter) plugin
- **⚡️ Optimizations & Fixes**: Multiple internal optimizations and bug fixes
- **⚖️ License Update**: Open source license changes

<details>
<summary><strong>📜 Version History</strong></summary>

### 🚀 v0.4.1
- **🐛 Bug Fixes**: Fixed Milvus search result processing issues
- **✨ Command Optimization**: Simplified `/memory list_records` command
- **✨ Model Support**: Added Google Gemini embedding model support

### 🚀 v0.4.0
- **✨ Auto Summarization**: Time-based automatic summarization feature
- **⚙️ Configuration**: Added timer configuration options
- **🛠️ Architecture**: Refactored context manager

### 🚀 v0.3.14
- **🐛 Critical Fix**: Resolved data insertion failure issues

### 🚀 v0.3.13
- **✨ Milvus Lite**: Added local lightweight database support

</details>

---

## ⚠️ Important Notes

### 🔄 Upgrading from Old Versions

**v0.6.0 is a major update, migration tools are recommended:**

1. **Backup Data**: Please backup important data before upgrading
2. **Use Migration Commands**: Migrate configuration through `/memory migrate_config`
3. **Validate Configuration**: Use `/memory validate_config` to verify
4. **Check Documentation**: Refer to [Migration Guide](docs/migration/REFACTOR_GUIDE.md)

### 📁 Data Storage

- **Plugin Data Directory**: All data stored in plugin-specific directory
- **Relative Path Support**: Relative paths in configuration are automatically processed
- **Data Isolation**: Complete isolation of data between different plugins

### 🔒 Data Security

> 🛡️ **Data Security Reminder**:  
> *"Protect your data like you protect important relationships - after all, no one wants their digital companion to suddenly 'lose memory'."*

---

## 🧩 Plugin Ecosystem

### 🚀 This Plugin Optimizations
- **DeepSeek API Optimization**: Integrated cache optimization code by [@Rail1bc](https://github.com/Rail1bc)
- **Token Savings**: Intelligently adjusts historical conversation content to improve cache hit rates

### ♻️ Recommended Plugins
- **[Composting Bucket Plugin](https://github.com/Rail1bc/astrbot_plugin_composting_bucket)**: DeepSeek API cache optimization
- **[Embedding Adapter](https://github.com/TheAnyan/astrbot_plugin_embedding_adapter)**: Enhanced embedding effects

---

## 🙏 Acknowledgments

- Thanks to **AstrBot Core Team** for the powerful platform
- Thanks to **[@Rail1bc](https://github.com/Rail1bc)** for DeepSeek API optimizations
- Thanks to all contributors and users for their support

**If this project helps you, please give it a Star ⭐!**

---

## 🌟 Contributors

[![GitHub Contributors](https://img.shields.io/github/contributors/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors)

<a href="https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=lxfight/astrbot_plugin_mnemosyne" alt="Contributor List" />
</a>

---

## ✨ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne)

_Every Star is a beacon for our progress! Thank you for your attention!_
