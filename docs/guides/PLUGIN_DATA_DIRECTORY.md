# 插件数据目录使用说明

## 📁 概述

从 v0.6.0 开始，Mnemosyne 插件使用 AstrBot 提供的插件专属数据目录来存储所有持久化数据。这确保了数据的隔离性和管理的便利性。

## 🔧 工作原理

### 数据目录获取

插件通过 `StarTools.get_data_dir("astrbot_plugin_mnemosyne")` 获取专属数据目录：

```python
self.plugin_data_path = StarTools.get_data_dir("astrbot_plugin_mnemosyne")
```

### 路径自动处理

插件会自动处理配置中的路径：

1. **相对路径**: 自动基于插件数据目录
2. **绝对路径**: 保持不变

```python
def _update_config_paths(self, config: dict) -> dict:
    """更新配置中的路径，使用插件专属数据目录"""
    import os
    
    # FAISS 数据路径处理
    if "faiss_data_path" in config:
        faiss_path = config["faiss_data_path"]
        if not os.path.isabs(faiss_path):
            config["faiss_data_path"] = os.path.join(self.plugin_data_path, faiss_path)
    
    # Milvus Lite 路径处理
    if "milvus_lite_path" in config and config["milvus_lite_path"]:
        milvus_path = config["milvus_lite_path"]
        if not os.path.isabs(milvus_path):
            config["milvus_lite_path"] = os.path.join(self.plugin_data_path, milvus_path)
    
    return config
```

## 📂 目录结构

典型的插件数据目录结构：

```
插件数据目录/
├── faiss_data/                    # FAISS 数据库目录
│   ├── mnemosyne_default/         # 集合目录
│   │   ├── index.faiss           # FAISS 索引文件
│   │   ├── metadata.pkl          # 元数据文件
│   │   └── info.json             # 集合信息
│   └── collections.json          # 集合列表
├── milvus.db                      # Milvus Lite 数据库文件
└── backup/                        # 备份文件（如果有）
    └── config_backup_20240623.json
```

## ⚙️ 配置示例

### FAISS 配置

```json
{
  "vector_database_type": "faiss",
  "faiss_data_path": "faiss_data",           // 相对路径，实际存储在插件数据目录下
  "faiss_index_type": "IndexFlatL2"
}
```

实际存储路径：`{插件数据目录}/faiss_data/`

### Milvus Lite 配置

```json
{
  "vector_database_type": "milvus",
  "milvus_lite_path": "milvus.db"            // 相对路径，实际存储在插件数据目录下
}
```

实际存储路径：`{插件数据目录}/milvus.db`

### 绝对路径配置

```json
{
  "vector_database_type": "faiss",
  "faiss_data_path": "/absolute/path/to/faiss"  // 绝对路径，直接使用
}
```

## 🔍 路径验证

可以通过 `/memory status` 命令查看实际使用的路径：

```
📊 Mnemosyne 插件状态报告

🔧 配置信息:
  数据库类型: faiss
  数据路径: /path/to/plugin/data/faiss_data
  
💾 数据库状态: ✅ 已连接
  集合: mnemosyne_default
  记录数: 150
```

## 🛠️ 开发者说明

### 在代码中使用

```python
# 获取插件数据目录
plugin_data_path = self.plugin_data_path

# 构建数据文件路径
data_file = os.path.join(plugin_data_path, "my_data.json")

# 确保目录存在
os.makedirs(os.path.dirname(data_file), exist_ok=True)

# 读写文件
with open(data_file, 'w') as f:
    json.dump(data, f)
```

### 配置处理

```python
# 在初始化数据库前处理配置路径
config_with_paths = self._update_config_paths(self.config.copy())

# 使用处理后的配置创建数据库
self.vector_db = VectorDatabaseFactory.create_database(
    db_type=db_type, 
    config=config_with_paths, 
    logger=self.logger
)
```

## 📋 最佳实践

### 1. 使用相对路径

**推荐**:
```json
{
  "faiss_data_path": "faiss_data"
}
```

**不推荐**:
```json
{
  "faiss_data_path": "./faiss_data"
}
```

### 2. 数据备份

定期备份插件数据目录：

```bash
# 备份整个插件数据目录
cp -r /path/to/plugin/data /path/to/backup/location
```

### 3. 迁移数据

在不同环境间迁移时，只需复制插件数据目录：

```bash
# 从旧环境复制到新环境
scp -r old_server:/path/to/plugin/data new_server:/path/to/plugin/data
```

### 4. 清理数据

清理插件数据时，删除整个插件数据目录：

```bash
# 谨慎操作：删除所有插件数据
rm -rf /path/to/plugin/data
```

## 🔧 故障排除

### 权限问题

如果遇到权限错误：

```bash
# 检查目录权限
ls -la /path/to/plugin/data

# 修复权限（如果需要）
chmod -R 755 /path/to/plugin/data
chown -R user:group /path/to/plugin/data
```

### 磁盘空间

监控插件数据目录的磁盘使用：

```bash
# 查看目录大小
du -sh /path/to/plugin/data

# 查看磁盘空间
df -h /path/to/plugin/data
```

### 数据恢复

如果数据损坏，可以从备份恢复：

```bash
# 停止 AstrBot
# 恢复数据
cp -r /path/to/backup/data /path/to/plugin/data
# 重启 AstrBot
```

## 🎯 优势

1. **数据隔离**: 每个插件的数据完全独立
2. **便于管理**: 统一的数据目录结构
3. **简化配置**: 相对路径自动处理
4. **易于备份**: 单一目录包含所有数据
5. **便于迁移**: 复制目录即可迁移所有数据
6. **权限控制**: 可以针对插件数据设置特定权限

## 📞 技术支持

如果在使用插件数据目录时遇到问题：

1. 使用 `/memory status` 检查当前状态
2. 查看 AstrBot 日志获取详细错误信息
3. 运行 `python test_plugin_data_path.py` 进行诊断
4. 在 GitHub Issues 寻求帮助
