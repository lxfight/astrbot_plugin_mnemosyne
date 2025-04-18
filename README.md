# 🧠 Mnemosyne - AstrBot 的长期记忆中枢

> *"Memory is the process of retaining information over time."*
> *"Memory is the means by which we draw on our past experiences in order to use this information in the present."*
> — (Paraphrased concepts based on memory research, attributing specific short quotes can be tricky)
>
> **让 AI 真正记住与你的每一次对话，构建持久的个性化体验。**

---

## 💬 支持与讨论

遇到问题或想交流使用心得？加入我们的讨论群：
[![加入QQ群](https://img.shields.io/badge/QQ群-953245617-blue?style=flat-square&logo=tencent-qq)](https://qm.qq.com/cgi-bin/qm/qr?k=WdyqoP-AOEXqGAN08lOFfVSguF2EmBeO&jump_from=webapi&authKey=tPyfv90TVYSGVhbAhsAZCcSBotJuTTLf03wnn7/lQZPUkWfoQ/J8e9nkAipkOzwh)

在这里，你可以直接与开发者和其他用户交流，获取更及时的帮助。

---

## 🎉 更新速览

<details>
<summary><strong>🚀 v0.3.14 (最新稳定版 - 强烈推荐)</strong></summary>

*   ✨ **🔧 Bug 修复:** 解决了 v0.3.13 版本中数据插入失败的关键问题。请务必更新至此版本以确保功能正常！
</details>

<details>
<summary><strong>🚀 v0.3.13</strong></summary>

*   ✨ **新功能:** 新增 `Milvus Lite` 支持！现在可以在本地运行轻量级向量数据库，无需额外部署完整的 Milvus 服务。（特别感谢提出此建议的群友！如果您看到，请来认领这份感谢 🙏）
*   ⚠️ **重要提示:** `Milvus Lite` 目前仅支持 `Ubuntu >= 20.04` 和 `MacOS >= 11.0`。
</details>

<details>
<summary><strong>📅 查看历史更新 (v0.3.4 -> v0.3.12)</strong></summary>

*   ✅ **Bug 修复:** 修复了指定 LLM 服务商后初始化错误的 Bug。
*   ➕ **配置更新:** 更新了配置架构，支持指定 LLM 服务商进行记忆总结。
*   🔧 **逻辑优化:** 会话时检查历史消息中是否有需要删除的长期记忆片段。
*   ⚡ **性能优化:** 使用异步方式处理同步 IO 操作，避免阻塞主线程。
*   🐛 **Bug 修复:** 调整了正则表达式的大小写敏感问题。
*   🚑 **紧急修复:** 增加对 `astrbot_max_context_length` 大小的判断，避免负数导致的错误。
*   ⚙️ **功能恢复:** 恢复了配置项 `历史上下文中保留的长期记忆数量 (contexts_memory_len)` 的作用。
*   🐛 **Bug 修复:** 修复了关于 `num_pairs` 配置项无法生效的问题，导致记忆总结时携带大量历史记录。
*   🗑️ **Bug 修复:** 修复了 `v0.3.3` 版本以来，调用 LLM 总结记忆时，旧记忆存在于上下文的问题。
*   🛠️ **指令修复:** 修复了 `/memory list_records` 指令错误。
</details>

---

## 🚀 快速开始

想要立刻体验 Mnemosyne 的强大记忆力？请查阅我们的快速入门指南：

➡️ **[如何正确且快速地食用本插件 (Wiki)](https://github.com/lxfight/astrbot_plugin_mnemosyne/wiki/%E5%A6%82%E4%BD%95%E6%AD%A3%E7%A1%AE%E4%B8%94%E5%BF%AB%E9%80%9F%E7%9A%84%E9%A3%9F%E7%94%A8%E6%9C%AC%E6%8F%92%E4%BB%B6)** ⬅️

---

## ⚠️ 重要提示：测试版本风险须知

❗️ **请注意：本插件目前仍处于活跃开发和测试阶段。**

### 1. 功能与数据风险
*   由于插件仍在快速迭代中，新功能的加入、代码重构或与 AstrBot 主程序的兼容性调整，**可能在某些情况下引发系统不稳定或数据处理异常**。
*   当前版本**尚未包含**完善的自动化数据迁移方案。这意味着在进行大版本更新时，**存在丢失历史记忆数据的风险**。

### 2. 使用建议
*   ✅ **强烈建议：** 在更新插件版本前，务必**备份重要数据**，包括但不限于：
    *   插件配置文件
    *   Milvus 数据（如果是独立部署的 Milvus，请参考其备份文档；如果是 Milvus Lite，请备份 `AstrBot/data/mnemosyne_data` 目录）
*   🧪 **推荐操作：** 如果条件允许，建议先在非生产环境（例如测试用的 AstrBot 实例）中测试新版本，确认无误后再更新到您的主环境。

> 🛡️ **数据安全箴言:**
> *"请像保护重要关系一样重视您的数据安全——毕竟，谁都不希望自己的数字伴侣突然'失忆'。"*

---

## 📦 Milvus 数据库安装 (可选)

如果您不使用 v0.3.13+ 版本新增的 `Milvus Lite` 模式，或者需要更强大的独立向量数据库，可以选择安装 Milvus：

*   **🐧 Linux (Docker):** [Milvus 独立版 Docker 安装指南](https://milvus.io/docs/zh/install_standalone-docker.md)
*   **💻 Windows (Docker):** [Milvus 独立版 Windows Docker 安装指南](https://milvus.io/docs/zh/install_standalone-windows.md)

> **提示:** 对于大多数个人用户和快速体验场景，`Milvus Lite` (v0.3.13+) 是更便捷的选择，无需额外安装。

---

## 🧩 插件生态推荐：优化 DeepSeek API 体验

**1. 本插件 (Mnemosyne v0.3+ 系列) 🚀**

*   Mnemosyne 插件自 `v0.3` 系列起，集成了由开发者 **[Rail1bc](https://github.com/Rail1bc)** 贡献的关键优化代码。
*   **核心优势**: 此优化专门针对 DeepSeek 官方 API 的缓存机制。通过智能调整发送给 API 的历史对话内容，能够**显著提高缓存命中率**。这意味着您可以更频繁地复用之前的计算结果，有效**降低 Token 消耗量** 💰，为您节省 API 调用成本。

**2. 堆肥桶 (Composting Bucket) 插件 ♻️**

*   除了对 Mnemosyne 的贡献，开发者 **Rail1bc** 还独立开发了一款名为 **“堆肥桶” (Composting Bucket)** 的 AstrBot 插件。
*   **主要功能**: 该插件专注于提升 DeepSeek API 的缓存利用效率。即使您不使用 Mnemosyne 的记忆功能，也可以将“堆肥桶”作为一个独立的增强工具，进一步优化缓存表现，减少不必要的 Token 开销。（“堆肥桶”对用户体验的影响较小，主要在后台优化）
*   **项目地址**: 感兴趣的用户可以访问了解详情：
    🔗 **[astrbot_plugin_composting_bucket on GitHub](https://github.com/Rail1bc/astrbot_plugin_composting_bucket)**

> ✨ 如果您是 DeepSeek API 用户，强烈推荐关注并尝试由 **Rail1bc** 带来的这些优秀工具，让您的 AI 体验更经济、更高效！

---

## 🙏 致谢

*   感谢 **AstrBot 核心开发团队** 提供的强大平台和技术支持。
*   感谢 **[Rail1bc](https://github.com/Rail1bc)** 对 DeepSeek API 优化提供的关键代码贡献。
*   感谢所有在 QQ 群和 GitHub Issues 中提出宝贵意见和反馈的用户。

**如果本项目给您带来了帮助或乐趣，请不吝点亮 Star ⭐ ！您的支持是我持续开发和改进的最大动力！**

发现 Bug？有好点子？请随时通过 [GitHub Issues](https://github.com/lxfight/astrbot_plugin_mnemosyne/issues) 告诉我们。每一条反馈我们都会认真对待。

---

## 🌟 贡献者

感谢所有为 Mnemosyne 项目做出贡献的朋友们！

[![GitHub Contributors](https://img.shields.io/github/contributors/lxfight/astrbot_plugin_mnemosyne?style=flat-square)](https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors)

<a href="https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=lxfight/astrbot_plugin_mnemosyne" alt="Contributor List" />
</a>

---

## ✨ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne)

_每一个 Star 都是我们前进的灯塔！感谢您的关注！_