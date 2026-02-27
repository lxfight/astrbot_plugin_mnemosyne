# Windows 新手完整部署教程

> 本教程面向完全不了解 Milvus 和 Docker 的 Windows 用户，将手把手教你完成 Mnemosyne 长期记忆插件的部署。

## 📋 前置要求

- Windows 10 或 Windows 11 操作系统
- 已安装并运行 AstrBot
- 基本的命令行操作能力

## 🎯 部署方案选择

根据你的需求选择合适的方案：

| 方案 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **Milvus Lite** | 个人使用、测试 | 无需安装额外软件，开箱即用 | 性能较低，数据量大时不稳定 |
| **Docker 部署** | 生产环境、多用户 | 性能好，稳定性高 | 需要安装 Docker Desktop |

**💡 建议**：新手或个人使用优先选择 **Milvus Lite**，简单快捷。

---

## 方案一：Milvus Lite 部署（推荐新手）

### 第一步：确认环境

1. **检查 Python 版本**
   - 打开命令提示符（Win+R 输入 `cmd`）
   - 输入 `python --version`
   - 确保版本 >= 3.8

2. **确认 AstrBot 正常运行**
   - 访问 `http://127.0.0.1:6185`（或你的 AstrBot 地址）
   - 能正常打开 WebUI 即可

### 第二步：安装插件

1. **在 AstrBot WebUI 中安装**
   - 打开 AstrBot 控制面板
   - 进入 **插件市场**
   - 搜索 `Mnemosyne`
   - 点击 **安装**

2. **等待安装完成**
   - 观察日志输出
   - 看到 "插件安装成功" 提示

### 第三步：配置插件

1. **进入插件配置页面**
   - 插件管理 → Mnemosyne → 配置

2. **填写基础配置**

   ```yaml
   # Milvus 连接配置
   milvus_mode: "lite"  # 使用 Lite 模式

   # 记忆总结配置
   num_pairs: 5         # 每5轮对话后总结
   top_k: 5             # 检索返回5条记忆
   score_threshold: 0.7 # 相似度阈值

   # Embedding 服务配置（必填）
   embedding_providers:
     - name: "silicon"
       type: "openai_compatible"
       api_base: "https://api.siliconflow.cn/v1"
       api_key: "你的API密钥"
       model: "BAAI/bge-m3"
   ```

3. **重启插件**
   - 点击 **保存配置**
   - 点击 **重启插件**

### 第四步：验证功能

1. **测试记忆存储**
   - 在任意聊天窗口与 Bot 对话 5 轮以上
   - 观察日志，应该看到类似输出：
     ```
     [Mnemosyne] 开始总结历史对话...
     [Mnemosyne] 记忆已存储到数据库
     ```

2. **测试记忆检索**
   - 提问与之前对话相关的问题
   - Bot 应该能回忆起之前的内容

3. **查看管理面板**（可选）
   - 访问 `http://127.0.0.1:8000`
   - 使用配置中的 API 密钥登录
   - 查看已存储的记忆列表

### 常见问题

#### Q1：提示 "milvus-lite is required"

**解决方案**：
```bash
# 在 AstrBot 虚拟环境中安装
cd D:\你的AstrBot路径
.venv\Scripts\activate
pip install pymilvus[milvus_lite]
```

#### Q2：记忆没有被总结

**检查清单**：
1. 对话轮数是否达到 5 轮（一问一答算 1 轮）
2. Embedding 服务是否配置正确
3. 查看日志是否有报错

**测试 Embedding 服务**：
- 在插件配置中点击 **测试连接**
- 确认显示 "连接成功"

#### Q3：检索不到记忆

**可能原因**：
1. 相似度阈值设置过高（默认 0.7）
2. 问题与之前对话不相关
3. 记忆尚未总结完成

**调整方法**：
```yaml
score_threshold: 0.6  # 降低阈值试试
top_k: 10             # 增加返回数量
```

---

## 方案二：Docker 部署 Milvus Standalone

### 第一步：安装 Docker Desktop

1. **下载 Docker Desktop**
   - 访问 [Docker 官网](https://www.docker.com/products/docker-desktop/)
   - 下载 Windows 版本

2. **安装 Docker Desktop**
   - 双击安装包
   - 保持默认设置
   - 安装完成后重启电脑

3. **验证安装**
   - 打开命令提示符
   - 输入 `docker --version`
   - 看到版本号即为成功

### 第二步：部署 Milvus

1. **创建工作目录**
   ```bash
   mkdir D:\milvus
   cd D:\milvus
   ```

2. **下载 docker-compose 配置文件**
   ```bash
   curl -o docker-compose.yml https://github.com/milvus-io/milvus/releases/download/v2.6.4/milvus-standalone-docker-compose.yml
   ```

3. **启动 Milvus**
   ```bash
   docker-compose up -d
   ```

4. **验证运行状态**
   ```bash
   docker-compose ps
   ```

   应该看到类似输出：
   ```
   NAME                COMMAND             STATUS
   milvus-standalone   ...                 Up
   milvus-etcd         ...                 Up
   milvus-minio        ...                 Up
   ```

### 第三步：配置插件

在 AstrBot WebUI 中配置：

```yaml
# Milvus 连接配置
milvus_mode: "standalone"
milvus_host: "127.0.0.1"
milvus_port: 19530

# 其余配置与 Lite 模式相同
```

### 第四步：验证连接

1. **测试端口连通性**
   ```bash
   # Windows PowerShell
   Test-NetConnection -ComputerName 127.0.0.1 -Port 19530
   ```

2. **在插件中测试连接**
   - 插件配置页面 → **测试 Milvus 连接**
   - 显示 "连接成功" 即可

### 常见问题

#### Q1：Docker 无法启动

**解决方案**：
1. 确认 Windows 虚拟化已启用
   - 任务管理器 → 性能 → CPU
   - 查看 "虚拟化" 是否为 "已启用"

2. 如未启用，需要在 BIOS 中开启
   - 重启电脑
   - 进入 BIOS（通常按 F2/F10/Del）
   - 找到 "Virtualization Technology" 并启用

#### Q2：docker-compose 命令找不到

**解决方案**：
```bash
# Docker Desktop 新版本使用 docker compose（无横杠）
docker compose up -d
docker compose ps
```

#### Q3：端口 19530 被占用

**检查端口占用**：
```bash
netstat -ano | findstr :19530
```

**解决方案**：
1. 修改 docker-compose.yml 中的端口映射
2. 或停止占用该端口的程序

---

## 🔧 跨 Docker Compose 部署（高级）

如果你的 AstrBot 也是 Docker 部署，且与 Milvus 不在同一个 docker-compose 文件中：

### 方法一：使用网络互联

1. **创建共享网络**
   ```bash
   docker network create milvus
   ```

2. **修改 Milvus 的 docker-compose.yml**
   ```yaml
   services:
     standalone:
       # ... 其他配置
       networks:
         - milvus

   networks:
     milvus:
       external: true
   ```

3. **修改 AstrBot 的 docker-compose.yml**
   ```yaml
   services:
     astrbot:
       # ... 其他配置
       networks:
         - astrbot_network
         - milvus

   networks:
     astrbot_network:
       driver: bridge
     milvus:
       external: true
   ```

4. **在插件中配置连接**
   ```yaml
   milvus_host: "milvus-standalone"  # 使用容器名而非 127.0.0.1
   milvus_port: 19530
   ```

### 方法二：使用主机网络

在 AstrBot 的 docker-compose.yml 中：
```yaml
services:
  astrbot:
    network_mode: "host"
```

然后使用 `127.0.0.1:19530` 连接 Milvus。

---

## 📊 性能优化建议

### 对于 Milvus Lite

```yaml
# 轻量配置
num_pairs: 8              # 减少总结频率
top_k: 3                  # 减少检索数量
use_session_filtering: true  # 启用会话过滤
```

### 对于 Milvus Standalone

```yaml
# 标准配置
num_pairs: 5
top_k: 5
score_threshold: 0.7

# 高负载配置
num_pairs: 10
top_k: 10
use_personality_filtering: true
```

---

## 🆘 获取帮助

- **QQ 群**：953245617
- **GitHub Issues**：https://github.com/lxfight/astrbot_plugin_mnemosyne/issues
- **官方文档**：https://github.com/lxfight/astrbot_plugin_mnemosyne

---

## 📝 附录：完整配置文件示例

### Milvus Lite 配置

```yaml
# Milvus 配置
milvus_mode: "lite"

# Embedding 配置
embedding_providers:
  - name: "silicon"
    type: "openai_compatible"
    api_base: "https://api.siliconflow.cn/v1"
    api_key: "sk-your-api-key"
    model: "BAAI/bge-m3"

# 记忆参数
num_pairs: 5
top_k: 5
score_threshold: 0.7
use_session_filtering: true
use_personality_filtering: false
personality_fallback: false

# 管理面板
admin_panel:
  enabled: true
  host: "127.0.0.1"
  port: 8000
  api_key: "your-secret-key"
```

### Milvus Standalone 配置

```yaml
# Milvus 配置
milvus_mode: "standalone"
milvus_host: "127.0.0.1"
milvus_port: 19530
milvus_user: ""
milvus_password: ""

# 其余配置同上
```

---

**更新时间**：2026-02-27
**插件版本**：v2.0.16
**维护者**：lxfight
