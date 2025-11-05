# 快速启动指南

本指南帮助您快速上手 Mnemosyne 长期记忆插件。

## 5 分钟快速部署

### 步骤 1：安装 Milvus

**方法 A：Docker 部署（推荐）**

```bash
# 下载配置文件
wget https://github.com/milvus-io/milvus/releases/download/v2.6.4/milvus-standalone-docker-compose.yml -O docker-compose.yml

# 启动服务
docker-compose up -d

# 验证运行状态
docker-compose ps
```

**方法 B：Milvus Lite（轻量级）**

```bash
pip install pymilvus
```

### 步骤 2：安装插件依赖

```bash
cd data/plugins/astrbot_plugin_mnemosyne
uv pip install -r requirements.txt
```

### 步骤 3：配置插件

在 AstrBot WebUI 中配置插件：

1. 打开 **插件管理** → **Mnemosyne**
2. 设置 Milvus 连接信息：
   - **主机地址**：`127.0.0.1`（本地部署）
   - **端口**：`19530`（默认端口）
   - **集合名称**：`default`（或自定义名称）
3. 配置记忆总结参数：
   - **对话轮数**：`5`（每 5 轮对话后自动总结）
   - **检索数量**：`5`（返回最相关的 5 条记忆）
   - **相似度阈值**：`0.7`（只返回相似度 ≥ 0.7 的记忆）

### 步骤 4：重启 AstrBot

```bash
# 在 AstrBot 根目录
python main.py
```

### 步骤 5：验证功能

**测试记忆存储**：
1. 与机器人进行 5 轮以上对话
2. 观察日志中的 `[Mnemosyne]` 信息
3. 应该看到"开始总结历史对话"的日志

**测试记忆检索**：
1. 提出与之前对话相关的问题
2. 机器人应该能够回忆起之前的内容

**查看 WebUI**：
1. 打开 AstrBot Dashboard
2. 进入 **Alkaid** → **长期记忆**
3. 查看已存储的记忆列表

## 常见问题快速解决

### Q1：无法连接 Milvus

**检查清单**：
```bash
# 1. 验证 Milvus 是否运行
docker ps | grep milvus

# 2. 检查端口是否开放
netstat -an | grep 19530

# 3. 测试连接
telnet 127.0.0.1 19530
```

**解决方案**：
- 确保 Docker 容器正在运行
- 检查防火墙设置
- 尝试使用 `localhost` 代替 `127.0.0.1`

### Q2：记忆没有被总结

**可能原因**：
1. 对话轮数未达到阈值（默认 5 轮）
2. LLM Provider 未正确配置
3. Embedding Provider 未配置

**检查方法**：
```bash
# 查看日志中的消息计数

# 检查 LLM 配置
# 在 AstrBot WebUI → 服务商配置 中确认
```

### Q3：Collection not loaded 错误

**说明**：此问题已在 v2.0.0 中修复。

**如果仍然出现**：
1. 检查插件版本是否为 v2.0.0+
2. 删除旧集合并重新创建：
   ```python
   # 在 Python 中执行
   from pymilvus import connections, utility
   connections.connect(host="127.0.0.1", port="19530")
   utility.drop_collection("default")
   # 重启 AstrBot
   ```



## 性能优化技巧

### 1. 调整对话轮数

**较小值（3-5 轮）**：
- ✅ 记忆更新频繁，内容更细致
- ❌ LLM 调用次数增加，成本上升

**较大值（8-12 轮）**：
- ✅ 减少 LLM 调用，降低成本
- ❌ 记忆更新不及时，可能丢失细节

**建议**：根据对话密度调整，一般用户建议 5-8 轮

### 2. 优化检索参数

**提高检索精度**：
```json
{
  "top_k": 3,           // 减少返回数量
  "score_threshold": 0.8  // 提高相似度门槛
}
```

**提高检索召回**：
```json
{
  "top_k": 10,          // 增加返回数量
  "score_threshold": 0.6  // 降低相似度门槛
}
```


**祝您使用愉快！** 🎉