# Mnemosyne 迁移命令使用示例

## 🚀 快速开始

### 场景一：新用户首次配置

如果您是新用户，推荐使用 FAISS 数据库：

```
# 1. 查看当前状态
/memory status

# 2. 如果显示需要迁移，执行配置迁移
/memory migrate_config

# 3. 验证配置
/memory validate_config

# 4. 查看帮助了解更多功能
/memory help
```

### 场景二：从旧版本升级

如果您已经在使用旧版本的 Mnemosyne：

```
# 1. 查看当前状态和配置
/memory status

# 2. 迁移配置到新格式
/memory migrate_config

# 3. 验证迁移结果
/memory validate_config

# 4. 重启插件以应用更改
```

### 场景三：从 Milvus 迁移到 FAISS

如果您想从 Milvus 切换到更简单的 FAISS：

```
# 1. 确认当前状态
/memory status

# 2. 执行数据迁移（需要管理员权限）
/memory migrate_to_faiss --confirm

# 3. 重启插件
# 4. 验证迁移结果
/memory status
```

### 场景四：从 FAISS 迁移到 Milvus

如果您需要企业级功能，可以迁移到 Milvus：

```
# 1. 先配置 Milvus 连接信息（在 AstrBot 配置界面）
# 2. 验证 Milvus 配置
/memory validate_config

# 3. 执行数据迁移（需要管理员权限）
/memory migrate_to_milvus --confirm

# 4. 重启插件
# 5. 验证迁移结果
/memory status
```

## 📁 数据存储说明

### 插件数据目录

v0.6.0 引入了插件专属数据目录管理：

- **自动管理**: 所有数据自动存储在 AstrBot 为插件分配的专属目录
- **路径配置**:
  - 相对路径（如 `faiss_data`）自动基于插件数据目录
  - 绝对路径保持不变
- **数据隔离**: 不同插件的数据完全隔离，避免冲突
- **便于管理**: 统一的数据目录便于备份和迁移

### 路径示例

```
插件数据目录: /path/to/astrbot/data/plugins/astrbot_plugin_mnemosyne/
├── faiss_data/          # FAISS 数据库文件
├── milvus.db           # Milvus Lite 数据库文件
└── config_backup.json  # 配置备份文件
```

## 📋 命令详解

### `/memory status` - 状态查看

**功能**: 显示插件当前状态和配置信息

**示例输出**:
```
📊 Mnemosyne 插件状态报告

🔧 配置信息:
  版本: v0.6.0
  数据库类型: faiss
  嵌入服务ID: your_provider_id
  迁移状态: ✅ 已迁移到 v0.6.0

💾 数据库状态: ✅ 已连接
  集合: mnemosyne_default
  记录数: 150
  向量维度: 1024

🤖 嵌入服务状态: ✅ 已初始化
  服务: AstrBot-Native
  模型: text-embedding-3-small
  维度: 1024
```

### `/memory migrate_config` - 配置迁移

**功能**: 将旧版本配置迁移到新格式

**使用场景**:
- 从 v0.5.x 升级到 v0.6.0
- 添加新的配置选项
- 保持向后兼容

**示例输出**:
```
🔄 开始迁移配置到新格式...
✓ 检测到 Milvus 配置，设置数据库类型为 milvus
✅ 配置迁移完成！新增配置项：
  - vector_database_type: milvus
  - faiss_data_path: ./faiss_data
  - faiss_index_type: IndexFlatL2
  - embedding_provider_id: 

⚠️ 注意：配置已更新，建议重启插件以应用更改。
```

### `/memory migrate_to_faiss --confirm` - 迁移到 FAISS

**功能**: 将数据从其他数据库迁移到 FAISS

**权限**: 需要管理员权限

**使用前提**:
- 当前数据库连接正常
- 有足够的磁盘空间

**示例流程**:
```
# 不带 --confirm 时显示确认信息
/memory migrate_to_faiss

⚠️ 数据库迁移确认 ⚠️
此操作将把数据从 milvus 迁移到 FAISS 数据库。
迁移过程中可能需要一些时间，请确保：
1. 当前数据库连接正常
2. 有足够的磁盘空间
3. 迁移期间避免其他操作

如果确认迁移，请执行：
/memory migrate_to_faiss --confirm

# 确认迁移
/memory migrate_to_faiss --confirm

🔄 开始迁移到 FAISS 数据库...
📦 创建 FAISS 数据库实例...
📋 开始迁移集合 'mnemosyne_default' 的数据...
✅ 数据迁移成功！
⚠️ 请重启插件以使用新的 FAISS 数据库。
```

### `/memory validate_config` - 配置验证

**功能**: 验证当前配置是否正确

**检查项目**:
- 数据库配置
- 嵌入服务配置
- 必要配置项

**示例输出**:
```
🔍 开始验证配置...
✅ faiss 数据库配置验证通过
✅ 嵌入服务配置验证通过
✅ 必要配置项检查通过

🎉 配置验证全部通过！插件应该可以正常工作。
```

### `/memory help` - 帮助信息

**功能**: 显示详细的命令帮助和使用指南

**包含内容**:
- 所有可用命令列表
- 使用示例
- 新功能介绍
- 最佳实践建议

## ⚠️ 注意事项

### 迁移前的准备

1. **备份数据**: 虽然迁移过程会保留原数据，但建议先备份重要数据
2. **检查权限**: 数据库迁移命令需要管理员权限
3. **确认配置**: 迁移前确保目标数据库配置正确
4. **停止其他操作**: 迁移期间避免其他插件操作

### 迁移后的验证

1. **重启插件**: 迁移完成后重启插件以应用更改
2. **检查状态**: 使用 `/memory status` 确认迁移成功
3. **测试功能**: 进行简单的对话测试确保功能正常
4. **查看日志**: 检查 AstrBot 日志确认无错误

### 常见问题

**Q: 迁移失败怎么办？**
A: 检查日志获取详细错误信息，确保数据库配置正确，必要时使用脚本工具迁移

**Q: 可以回滚迁移吗？**
A: 配置迁移可以手动回滚，数据迁移建议提前备份

**Q: 迁移会丢失数据吗？**
A: 正常情况下不会，但建议提前备份重要数据

**Q: 需要重启 AstrBot 吗？**
A: 通常只需重启插件，不需要重启整个 AstrBot

## 🎯 最佳实践

1. **新用户**: 直接使用 FAISS 配置，简单高效
2. **升级用户**: 先迁移配置，再根据需要选择数据库
3. **企业用户**: 考虑使用 Milvus 获得更好的扩展性
4. **测试环境**: 先在测试环境验证迁移流程
5. **定期备份**: 定期备份配置和数据文件
