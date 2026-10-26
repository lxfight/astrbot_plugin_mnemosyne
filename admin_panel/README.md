# Mnemosyne 管理视图

该目录提供长期记忆管理视图的数据模型、服务和监控逻辑。用户界面位于 `views/panel/`，HTTP 路由由根目录的 `web_api.py` 注册。

管理视图运行在 AstrBot Dashboard 内，不启动独立 Web 服务器，不监听单独端口，也不维护独立 API Key。访问权限继承 AstrBot Dashboard 管理员会话。

## 目录结构

| 路径 | 职责 |
| --- | --- |
| `views/panel/` | Dashboard 插件视图、前端组件与 `AstrBotPluginView` bridge |
| `web_api.py` | 注册监控、记忆查询、编辑、删除、导出和配置 API |
| `admin_panel/models/` | 搜索请求、分页结果和监控数据结构 |
| `admin_panel/services/memory_service.py` | 记忆查询、统计、编辑与导出 |
| `admin_panel/services/monitoring_service.py` | 运行状态、资源占用与延迟指标 |

## 访问方式

1. 使用 AstrBot 管理员账号登录 Dashboard。
2. 进入 **Alkaid**。
3. 打开 **长期记忆**。

前端通过 `window.AstrBotPluginView` 获取宿主上下文，并调用 AstrBot 注入的插件 API bridge。页面不会自行保存 Dashboard 凭据。

## API

路由统一以 `/astrbot_plugin_mnemosyne` 为前缀，通过 `context.register_web_api` 注册。主要入口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/monitoring/dashboard` | 系统状态、指标与资源汇总 |
| `GET` / `POST` | `/memories/search` | 分页检索记忆 |
| `POST` | `/memories/delete` | 批量删除 |
| `POST` | `/memories/{memory_id}/update` | 更新记忆正文并重新生成向量 |
| `POST` | `/memories/{memory_id}/delete` | 删除单条记忆 |
| `POST` | `/memories/session/{session_id}/delete` | 删除会话记忆 |
| `GET` | `/memories/export` | 导出 CSV 或 JSON 附件 |
| `GET` | `/config` | 读取脱敏后的插件配置 |
| `POST` | `/config` | 保存插件配置 |

成功响应直接返回数据体；失败响应为 `{"status": "error", "message": "..."}`。导出接口使用 AstrBot Web API 的流式响应返回附件。

## 开发与验证

```powershell
uv run --no-project --python D:\AstrBot\.venv\Scripts\python.exe python -m pytest tests\test_web_api_core_paths.py -q
```

接口测试使用 Quart 兼容层模拟 AstrBot Web API；真实 AstrBot 环境应同时验证 `astrbot.api.web` 请求上下文和导出响应。

完整用户文档参见 [管理面板](https://lxfight.github.io/astrbot_plugin_mnemosyne/guide/admin-panel)。
