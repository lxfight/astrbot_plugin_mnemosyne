# 管理面板快速开始指南

## 🚀 首次使用

### 方法一：使用自动生成的 Token（推荐新手）

1. **启动插件**
   - 启动 AstrBot 和 Mnemosyne 插件

2. **查看日志**
   - 在日志中找到类似以下的输出：
   ```
   🔒 已生成动态强 token 并保存到: <插件数据目录>/admin_panel/.api_token
      Token: a1b2c3d4e5f6...（完整64字符）
   ```

3. **保存 Token**
   - 复制完整的 token（64个字符）
   - 妥善保存，后续访问需要使用

4. **访问管理面板**
   - 打开浏览器访问管理面板地址
   - 首次访问时会弹出对话框
   - 粘贴复制的 token
   - 点击确定

5. **完成！**
   - Token 会自动保存在浏览器中
   - 下次访问无需重新输入

### 方法二：配置自定义密钥（推荐高级用户）

1. **编辑配置文件**
   - 找到插件配置文件（通常在 `config/` 目录）
   - 添加或修改以下配置：
   ```json
   {
     "admin_panel": {
       "api_key": "your-custom-secure-password"
     }
   }
   ```

2. **重启插件**
   - 保存配置后重启 AstrBot

3. **访问管理面板**
   - 使用您设置的自定义密钥登录

## 📍 Token 位置

### 自动生成的 Token
- 文件路径：`<AstrBot插件数据目录>/admin_panel/.api_token`
- 插件数据目录由 `StarTools.get_data_dir()` 获取
- 可以用文本编辑器打开查看

### 自定义密钥
- 配置文件：`config/astrbot_plugin_mnemosyne.json`（或对应配置文件）
- 字段：`admin_panel.api_key`

## ❓ 常见问题

### Q: 忘记了 Token 怎么办？

**A: 自动生成的 Token**
```bash
# Windows（假设插件数据目录为 data/plugins/mnemosyne）
type data\plugins_data\mnemosyne\admin_panel\.api_token

# Linux/Mac
cat data/plugins_data/mnemosyne/admin_panel/.api_token
```

**提示**：实际路径取决于 AstrBot 的配置和 `StarTools.get_data_dir()` 的返回值。

**A: 自定义密钥**
- 查看配置文件中的 `admin_panel.api_key` 字段

### Q: 如何重置 Token？

**A: 自动生成的 Token**
1. 删除文件：`<插件数据目录>/admin_panel/.api_token`
2. 重启插件
3. 在日志中查看新生成的 token

**A: 自定义密钥**
1. 修改配置文件中的 `admin_panel.api_key`
2. 重启插件

### Q: 浏览器显示"认证失败"？

**A: 清除已保存的 Token**
1. 按 F12 打开浏览器开发者工具
2. 切换到 Console（控制台）标签
3. 输入并执行：
   ```javascript
   localStorage.removeItem('mnemosyne_api_key')
   ```
4. 刷新页面，重新输入正确的 token

### Q: 如何更改密钥？

**A: 步骤**
1. 修改配置文件中的 `api_key` 或删除自动生成的 token 文件
2. 重启插件
3. 在所有浏览器中清除旧的 token（见上方方法）
4. 使用新 token 登录

## 🔒 安全提醒

- ✅ **务必保管好您的 Token**
- ✅ **不要与他人分享 Token**
- ✅ **定期更换密钥（建议每3-6个月）**
- ✅ **使用 HTTPS 访问管理面板（生产环境）**
- ❌ **不要将 Token 提交到版本控制系统**
- ❌ **不要在公开场合展示包含 Token 的截图**

## 📚 更多信息

详细的安全机制说明请参阅：[SECURITY.md](./SECURITY.md)

## 💡 提示

- Token 在浏览器中保存，不会在每次访问时都要求输入
- 如果更换浏览器或清除浏览器数据，需要重新输入 token
- 建议将 token 保存在密码管理器中