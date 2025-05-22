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

我们持续改进，以下是本插件的近期更新亮点和重要里程碑：

### 🚀 v0.5.0 (最新版本)

*   🔗 **生态兼容:** 增加了对 [astrbot_plugin_embedding_adapter](https://github.com/TheAnyan/astrbot_plugin_embedding_adapter) 插件的兼容支持，现在可以与该插件联动，获取更优质的 embedding 效果。特别感谢 [@TheAnyan](https://github.com/TheAnyan) 的贡献！
*   ⚡️ **优化与修复:** 进行了多项内部优化，并修复了若干已知问题，提升了整体稳定性和用户体验。
*   ⚖️ **协议更新:** 插件的开源协议已进行变更，请查阅项目根目录下的 `LICENSE` 文件以获取详情。

### 🚀 v0.4.1

*   🐛 **Bug 修复:** 修复了在某些特定环境（如 pymilvus 2.5.4）下，处理 Milvus 搜索结果可能引发的 `TypeError: 'SequenceIterator' object is not iterable` 问题。特别感谢 [@HikariFroya](https://github.com/HikariFroya) 发现并贡献了解决方案！
*   ✨ **指令优化:** 简化了 `/memory list_records` 指令的使用，使其更专注于查询最新的记忆记录。
    *   命令格式变更为：`/memory list_records [collection_name] [limit]`，**移除了 `offset` 参数**。
    *   现在，您只需指定需要查看的记录数量 (`limit`)，系统将自动获取符合条件的所有记录（在安全上限内），并从中选取最新的几条按时间倒序显示，无需再手动计算偏移量，大大提升了便捷性。
*   ✨ **模型支持:** 嵌入模型现在增加了对 Google Gemini 嵌入模型的支持。感谢 [@Yxiguan](https://github.com/Yxiguan) 提供的关键代码！

### 🚀 v0.4.0

*   ✨ **核心新功能: 基于时间的自动总结**:
    *   插件内部集成计时器，当用户和BOT之间的消息长时间未被总结时（即使没有新的互动），系统将自动触发对先前历史消息的总结，有效减少手动总结的频率和遗漏。
*   ⚙️ **新增配置项**: 引入了用于自定义计时器间隔时间 (`auto_summary_interval`) 和总结阈值时间 (`auto_summary_threshold`) 的配置项，用户可根据需求灵活调整自动总结行为。
*   🛠️ **架构优化**: 重构了上下文管理器，优化了会话历史的存储和获取逻辑，显著提升了效率和稳定性。
*   🏗️ **后台任务**: 在主程序中完善了后台自动总结检查任务的启动与停止逻辑，确保该功能稳定可靠运行。

<details>
<summary><strong>📜 历史版本回顾 (v0.3.14 及更早)</strong></summary>

### 🚀 v0.3.14

*   🐛 **关键修复:** 解决了 v0.3.13 版本中导致数据插入失败的重大问题。**强烈建议所有用户更新至此版本以确保插件正常运行！**

### 🚀 v0.3.13

*   ✨ **新功能:** 新增 `Milvus Lite` 支持！现在可以在本地运行轻量级向量数据库，无需复杂部署完整的 Milvus 服务，极大简化了入门门槛和本地开发体验。（特别感谢提出此建议的社区群友！）
*   ⚠️ **重要提示:** `Milvus Lite` 目前仅支持 `Ubuntu >= 20.04` 和 `MacOS >= 11.0` 操作系统环境。

### 📜 v0.3.12 及更早版本 (主要优化与修复)

*   ✅ **核心修复:** 包含了多个关键 Bug 修复、紧急问题处理和指令逻辑修正，提升了插件的稳定性和健壮性。
*   🔧 **性能与逻辑优化:** 对会话历史检查、异步IO处理等核心模块进行了优化，有效提升了运行效率和响应速度。
*   ⚙️ **配置与功能完善:** 更新了配置架构以支持更多自定义选项，并恢复或优化了部分早期版本的功能设定，以满足更多使用场景的需求。

*此范围内包含了多次迭代的更新内容，上述为主要类别总结。如需查看更详细的历史更新日志，请查阅项目的 Release Notes 或 Git Commit 历史记录。*
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