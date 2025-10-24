# Mnemosyne 管理面板 - 安全机制说明

## 🔒 强制认证保护

从本版本开始，Mnemosyne 管理面板实施了**强制认证机制**，不再允许无 token 的访问。

## 安全更新内容

### 1. 动态强 Token 生成

- **自动保护**：如果用户未配置 `admin_panel.api_key`，系统会自动生成一个 64 字符的加密安全 token
- **持久化存储**：自动生成的 token 会保存到 `data/admin_panel/.api_token` 文件中
- **文件权限**：token 文件设置为仅所有者可读写（Unix 权限 0600）

### 2. 强制认证机制

- **不可禁用**：认证已强制启用，即使配置为空也会生成动态 token
- **所有路由保护**：所有 API 端点都要求有效的 API Key
- **时序攻击防护**：使用 `secrets.compare_digest()` 进行常量时间比较

### 3. 前端安全集成

- **自动认证**：前端会自动在所有 API 请求中添加 `X-API-Key` header
- **本地存储**：API Key 存储在浏览器 localStorage 中（仅前端可见）
- **认证失败处理**：401 错误时自动提示重新输入 token

## 使用指南

### 配置自定义 API Key（推荐）

在插件配置文件中设置：

```json
{
  "admin_panel": {
    "api_key": "your-secure-api-key-here"
  }
}
```

**建议**：使用至少 32 字符的强密码，包含大小写字母、数字和特殊字符。

### 使用自动生成的 Token

1. 启动插件后，查看日志输出
2. 找到类似以下的信息：

```
🔒 已生成动态强 token 并保存到: <插件数据目录>/admin_panel/.api_token
   Token: a1b2c3d4e5f6...
   请妥善保管此 token，用于访问管理面板。
```

3. 复制 token 并在首次访问管理面板时输入

### 查找已生成的 Token

如果忘记了自动生成的 token，可以在以下位置找到：

```
<AstrBot插件数据目录>/admin_panel/.api_token
```

**注意**：插件数据目录由 `StarTools.get_data_dir()` 获取，通常位于 AstrBot 的 `data/` 目录下。

使用文本编辑器打开该文件即可查看完整 token。

## 安全最佳实践

### ✅ 推荐做法

1. **使用自定义密钥**：在配置文件中设置强密码
2. **定期更换**：定期更新 API Key
3. **妥善保管**：不要将 API Key 提交到版本控制系统
4. **HTTPS 传输**：在生产环境使用 HTTPS 保护传输安全
5. **限制访问**：仅在可信网络环境下访问管理面板

### ❌ 避免做法

1. 不要使用简单或默认密码
2. 不要在公共网络上暴露管理面板
3. 不要与他人共享 API Key
4. 不要在日志或截图中泄露完整 token

## 技术细节

### Token 生成

- 使用 Python `secrets.token_hex(32)` 生成
- 输出 64 字符的十六进制字符串
- 密码学安全的随机数生成器

### 认证流程

1. 客户端在 HTTP header 中发送 `X-API-Key`
2. 服务器使用常量时间比较验证 token
3. 验证通过则允许访问，否则返回 401 Unauthorized

### 文件结构

```
<AstrBot插件数据目录>/
└── admin_panel/
    └── .api_token          # 自动生成的 token（如果未配置）
```

**说明**：所有持久化数据都存储在由 `StarTools.get_data_dir()` 返回的标准插件数据目录中，确保与 AstrBot 框架的一致性。

## 安全漏洞修复

本次更新修复了以下安全漏洞：

1. **CVE-未编号**：允许无认证访问管理面板
   - 影响：未授权用户可以访问所有管理功能
   - 修复：实施强制认证机制

2. **CVE-未编号**：监控路由缺少认证保护
   - 影响：敏感的系统信息可被任意访问
   - 修复：为所有监控路由添加 `@auth.require_auth` 装饰器

3. **CVE-未编号**：时序攻击风险
   - 影响：攻击者可能通过时序分析推断 token
   - 修复：使用 `secrets.compare_digest()` 进行恒定时间比较

## 迁移指南

### 从旧版本升级

如果您从没有强制认证的旧版本升级：

1. **首次启动**：系统会自动生成 token 并显示在日志中
2. **记录 Token**：务必保存日志中显示的 token
3. **配置密钥**（可选）：建议在配置文件中设置自定义 API Key

### 故障排除

**问题**：忘记了 API Key
**解决**：
- 自动生成的 token：查看 `data/admin_panel/.api_token` 文件
- 自定义密钥：查看插件配置文件

**问题**：认证一直失败
**解决**：
1. 清除浏览器 localStorage：`localStorage.removeItem('mnemosyne_api_key')`
2. 重新输入正确的 API Key
3. 检查服务器日志确认 token hash

**问题**：需要重置 token
**解决**：
- 删除 `data/admin_panel/.api_token` 文件
- 重启插件，系统会生成新 token

## 联系与支持

如有安全问题或疑问，请通过以下方式联系：

- GitHub Issues: https://github.com/lxfight/astrbot_plugin_mnemosyne/issues
- 标题请包含 `[SECURITY]` 前缀

## 更新日志

### v0.5.2 (2025-10-24)

- ✨ 新增：强制认证机制
- ✨ 新增：自动动态 token 生成
- 🔒 修复：允许无认证访问的安全漏洞
- 🔒 修复：监控路由缺少认证保护
- 🔒 修复：时序攻击风险
- 📝 新增：安全文档和使用指南