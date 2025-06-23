# Mnemosyne v0.6.0 重构指南

## 🚀 重大更新概述

Mnemosyne 插件已完成重大重构，新版本 v0.6.0 带来了以下重要改进：

### ✨ 新功能特性

1. **多向量数据库支持**
   - 新增 FAISS 向量数据库支持（本地高性能）
   - 保持 Milvus 支持（分布式企业级）
   - 统一的数据库接口，轻松切换

2. **AstrBot 原生集成**
   - 深度集成 AstrBot 原生嵌入服务
   - 支持 EmbeddingProvider 系统
   - 向后兼容传统 API 配置

3. **现代化架构**
   - 统一的向量数据库抽象层
   - 工厂模式管理数据库创建
   - 适配器模式统一嵌入服务
   - 改进的错误处理和日志系统

## 📋 配置迁移

### 新增配置项

```json
{
  "vector_database_type": "faiss",           // 新增：数据库类型选择
  "embedding_provider_id": "",               // 新增：AstrBot 原生嵌入服务 ID
  "faiss_config": {                          // 新增：FAISS 配置对象
    "faiss_data_path": "faiss_data",         // FAISS 数据路径（相对于插件数据目录）
    "faiss_index_type": "IndexFlatL2",       // FAISS 索引类型
    "faiss_nlist": 100                       // IVF 索引参数
  }
}
```

### 📁 插件数据目录

v0.6.0 引入了插件专属数据目录管理：

- **自动路径管理**: 所有持久化数据自动存储在插件专属目录
- **相对路径支持**: 配置中的相对路径自动基于插件数据目录
- **绝对路径保持**: 绝对路径配置保持不变
- **数据隔离**: 不同插件的数据完全隔离

### 兼容性说明

- ✅ 所有旧配置项保持兼容
- ✅ 自动检测并迁移配置
- ✅ 提供迁移工具辅助升级

## 🔧 使用迁移功能

### 方式一：通过命令迁移（推荐）

在 AstrBot 中直接使用命令进行迁移，无需额外脚本：

```
# 查看当前状态
/memory status

# 迁移配置到新格式
/memory migrate_config

# 迁移到 FAISS 数据库
/memory migrate_to_faiss --confirm

# 迁移到 Milvus 数据库
/memory migrate_to_milvus --confirm

# 验证配置
/memory validate_config

# 查看帮助
/memory help
```

### 方式二：使用迁移脚本

```bash
# 基本迁移（保持现有数据库类型）
python migration_tool.py --config your_config.json

# 迁移到 FAISS
python migration_tool.py --config your_config.json --target-db faiss

# 仅迁移配置，不迁移数据
python migration_tool.py --config your_config.json --config-only
```

### 迁移命令详细说明

#### 1. 查看状态 `/memory status`
- 显示当前数据库类型和连接状态
- 显示嵌入服务配置信息
- 显示迁移状态和版本信息
- 列出可用的迁移命令

#### 2. 配置迁移 `/memory migrate_config`
- 自动检测现有配置类型
- 添加新版本所需的配置项
- 保持所有现有配置不变
- 标记迁移版本信息

#### 3. 数据库迁移
**迁移到 FAISS**: `/memory migrate_to_faiss --confirm`
- 适合个人用户和小团队
- 本地存储，无需额外服务
- 高性能向量搜索
- 简单配置和维护

**迁移到 Milvus**: `/memory migrate_to_milvus --confirm`
- 适合企业级应用
- 支持分布式部署
- 需要预先配置 Milvus 连接信息
- 可扩展性强

#### 4. 配置验证 `/memory validate_config`
- 验证数据库配置是否正确
- 验证嵌入服务配置
- 检查必要配置项
- 提供修复建议

#### 5. 获取帮助 `/memory help`
- 显示所有可用命令
- 包含使用示例和说明
- 新功能介绍
- 最佳实践建议

### 手动配置

如果您偏好手动配置，请参考以下示例：

#### FAISS 配置（推荐新用户）

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

#### Milvus 配置（现有用户）

```json
{
  "vector_database_type": "milvus",
  "milvus_lite_path": "./milvus.db",
  "embedding_provider_id": "your_embedding_provider_id",
  "LLM_providers": "your_llm_provider_id"
}
```

## 🧪 测试重构结果

运行测试脚本验证重构是否成功：

```bash
python test_refactored_plugin.py
```

测试内容包括：
- 向量数据库工厂功能
- FAISS 数据库操作
- 嵌入服务适配器
- 向后兼容性验证

## 📊 性能对比

| 特性 | FAISS | Milvus |
|------|-------|--------|
| 搜索速度 | 极快 | 快 |
| 内存使用 | 低 | 中等 |
| 部署复杂度 | 简单 | 中等 |
| 扩展性 | 单机 | 分布式 |
| 推荐场景 | 个人用户 | 企业用户 |

## 🔍 故障排除

### 常见问题

1. **FAISS 导入错误**
   ```bash
   pip install faiss-cpu
   # 或 GPU 版本
   pip install faiss-gpu
   ```

2. **配置验证失败**
   - 检查 `vector_database_type` 是否正确
   - 验证对应数据库的配置参数
   - 使用迁移工具自动修复

3. **数据迁移失败**
   - 确保源数据库可访问
   - 检查目标数据库配置
   - 查看详细错误日志

### 日志调试

新版本使用 AstrBot 统一日志系统：

```
[FaissManager] Successfully initialized FAISS database
[EmbeddingAdapter] Using AstrBot native embedding provider
[Mnemosyne] Successfully created collection with FAISS backend
```

## 🎯 最佳实践

### 选择数据库后端

**选择 FAISS 如果：**
- 个人使用或小团队
- 希望简单部署
- 追求极致性能
- 数据量适中（< 100万向量）

**选择 Milvus 如果：**
- 企业级应用
- 需要分布式部署
- 大规模数据（> 100万向量）
- 需要高级功能

### 嵌入服务配置

**推荐配置顺序：**
1. 使用 AstrBot 原生嵌入服务（`embedding_provider_id`）
2. 使用传统 OpenAI API
3. 使用传统 Gemini API

### 性能优化

**FAISS 优化：**
```json
{
  "faiss_index_type": "IndexIVFFlat",  // 大数据集使用
  "faiss_nlist": 100                   // 调整聚类数量
}
```

**Milvus 优化：**
```json
{
  "vector_search_timeout": 30,         // 增加超时时间
  "top_k": 5                          // 调整检索数量
}
```

## 🔄 回滚方案

如果遇到问题需要回滚：

1. **恢复配置**：
   ```bash
   # 从备份恢复
   cp mnemosyne_backup_*/config_backup.json your_config.json
   ```

2. **恢复数据**：
   - FAISS：删除 `faiss_data` 目录
   - Milvus：恢复 Milvus 数据文件

3. **重新安装旧版本**：
   ```bash
   # 如果需要，可以回退到旧版本
   git checkout v0.5.1
   ```

## 📞 获取帮助

如果在重构过程中遇到问题：

1. **查看日志**：检查 AstrBot 日志获取详细错误信息
2. **运行测试**：使用 `test_refactored_plugin.py` 诊断问题
3. **社区支持**：在 GitHub Issues 或 QQ 群寻求帮助
4. **文档参考**：查阅完整的 README.md 文档

## 🎉 享受新功能

重构完成后，您可以享受：

- 🚀 更快的向量搜索（FAISS）
- 🔧 更简单的配置管理
- 🛡️ 更好的错误处理
- 📈 更高的系统稳定性
- 🔄 更灵活的扩展能力

感谢您使用 Mnemosyne v0.6.0！
