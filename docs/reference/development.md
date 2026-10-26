# 本地开发与文档部署

本页面向修改插件代码或文档的贡献者。Python 测试和 VitePress 文档构建使用独立工具链。

## 环境

- Python 3.12 或更高版本（与 AstrBot 4.29 保持一致）
- Node.js 20 或更高版本
- AstrBot 开发环境及可用的 LLM、Embedding Provider

## 安装依赖

```bash
uv venv --python 3.12
uv pip install -r requirements.txt pytest pytest-asyncio ruff
npm ci
```

## 运行测试

```bash
uv run pytest tests -q
uv run ruff check --select E,F --ignore E501 --exclude tests .
```

`tests/` 中的部分历史回归脚本只用于本地诊断，当前不纳入 CI 的 Ruff 范围。新增测试应保持 E/F 规则可检查。

## 构建文档

```bash
npm run docs:dev
npm run docs:build
npm run docs:preview
```

开发服务器默认监听 `0.0.0.0`。生产构建输出到 `docs/.vitepress/dist`。

部署到 GitHub Pages 项目路径时，需要设置页面基路径：

```powershell
$env:DOCS_BASE='/astrbot_plugin_mnemosyne/'
npm run docs:build
```

```bash
DOCS_BASE=/astrbot_plugin_mnemosyne/ npm run docs:build
```

## 文档结构

| 路径 | 内容 |
| --- | --- |
| `docs/guide/` | 中文安装、配置、管理和性能指南。 |
| `docs/reference/` | 中文架构、开发和故障排查参考。 |
| `docs/en/` | 对应的英文页面。 |
| `docs/.vitepress/` | 导航、站点配置、主题和构建输出。 |
| `docs/public/` | 不经过 Markdown 处理、直接发布的静态资源。 |

新增用户可见页面时，同时补充中英文内容和 `.vitepress/config.ts` 中的导航条目。

## GitHub Pages

`.github/workflows/docs.yml` 在 `main` 分支的文档或构建配置变更后执行：

1. 使用 `npm ci` 安装锁定依赖。
2. 使用 Pages 配置给出的基路径作为 `DOCS_BASE` 构建 VitePress。
3. 上传静态产物并部署到 GitHub Pages。

首次发布前，在仓库 **Settings → Pages** 中把 Source 设为 **GitHub Actions**。站点地址为 <https://lxfight.github.io/astrbot_plugin_mnemosyne/>。

CI 使用 `uv` 创建 Python 3.12 环境并安装测试依赖，同时执行 Ruff、pytest 与 VitePress 构建。导航、链接或 Markdown 处理出错时，Pull Request 会在合并前失败。
