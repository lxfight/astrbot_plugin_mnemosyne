# 🧠 Mnemosyne - AstrBot的长期记忆中枢

> "记忆造就了我们的存在" —— 神经科学家Eric Kandel
> 
> 让AI真正记住与你的每一次对话

---

## 相关支持与讨论

如您需要更及时的关于本插件使用的帮助，可以加入群聊：`953245617`与开发者和其他用户进一步讨论

---

<div style="border: 1px solid #ddd; padding: 10px; margin-bottom: 15px; border-radius: 5px; background-color: #f8f8f8;">
<h2>🎉 更新速览 🎉</h2>

<div style="border-bottom: 1px solid #eee; padding-bottom: 5px; margin-bottom: 5px;">
    <h4>🚀 v0.3.13</h4>
    <ul>
        <li>✨ <strong>新增 `Milvus Lite` 支持：</strong> 可以在本地使用极其轻量的数据库，无需部署完整 Milvus！（感谢提供建议的群友！但是我忘记是谁了，希望可以来认领一下）</li>
        <li>⚠️ <strong>重要提示：</strong> `Milvus Lite` 仅支持 `Ubuntu >= 20.04` 和 `MacOS >= 11.0`。</li>
    </ul>
</div>

<details>
    <summary>🔨 v0.3.4 -> v0.3.12</summary>
    <ul>
      <li>✅ <strong>Bug 修复：</strong> 修复了指定 LLM 服务商后初始化错误的 Bug。</li>
      <li>➕ <strong>配置更新：</strong> 更新了配置架构，支持指定 LLM 服务商进行记忆总结。</li>
      <li>🔧 <strong>逻辑优化：</strong> 会话时检查历史消息中是否有需要删除的长期记忆片段。</li>
      <li>⚡ <strong>性能优化：</strong> 使用异步方式处理同步 IO 操作，避免阻塞主线程。</li>
      <li>🐛 <strong>Bug 修复：</strong> 调整了正则表达式的大小写敏感问题。</li>
      <li>🚑 <strong>紧急修复：</strong> 增加对 `astrbot_max_context_length` 大小的判断，避免负数导致的错误。</li>
      <li>⚙️ <strong>功能恢复：</strong> 恢复了配置项 `历史上下文中保留的长期记忆数量 (contexts_memory_len)` 的作用。</li>
      <li>🐛 <strong>Bug 修复：</strong> 修复了关于 `num_pairs` 配置项无法生效的问题，导致记忆总结时携带大量历史记录。</li>
      <li>🗑️ <strong>Bug 修复：</strong> 修复了 `v0.3.3` 版本以来，调用 LLM 总结记忆时，旧记忆存在于上下文的问题。</li>
      <li>🛠️ <strong>指令修复：</strong> 修复了 `/memory list_records` 指令错误。</li>
    </ul>
</details>
</div>




---

## 使用提醒

❗️**重要提示：本插件当前仍为测试版本**

### 1. 功能风险说明
- 由于插件仍在开发阶段，新功能的迭代、与AstrBot的兼容性调整等更新**可能引发系统不稳定或数据异常**
- 当前版本尚未实现自动数据迁移机制，更新操作**可能导致历史数据丢失**

### 2. 使用建议
✅ 建议操作：
- 在更新前，请务必**备份重要配置文件及聊天记录**
- 建议在非生产环境先行测试新版本功能

⚠️ 特别注意：
> "请像保护重要关系一样重视数据安全——毕竟谁都不希望自己的数字伴侣突然'失忆'呢"

---

### Milvus 数据库安装

> 在linux系统使用Docker安装详见[linux安装教程](https://milvus.io/docs/zh/install_standalone-docker.md)

> 在Windows系统使用Docker安装详见[Windows安装教程](https://milvus.io/docs/zh/install_standalone-windows.md)


### 🧩 插件推荐：优化 DeepSeek API 体验

**1. 本插件 (v0.3 系列) 🚀**

*   在 Mnemosyne 插件的 `v0.3` 系列版本中，一项重要的优化来自于开发者 **[Rail1bc](https://github.com/Rail1bc)** 的杰出贡献。
*   他提供的代码专门针对 DeepSeek 官方 API 的缓存机制进行了深度优化。
*   **核心优势**：通过改进历史对话中的存储内容，该优化能够**极大程度地提高缓存命中概率**，这意味着您可以更频繁地复用之前的计算结果，从而有效**降低 Token 的实际消耗量** 💰，节省成本。

**2. 堆肥桶 (Composting Bucket) 插件 ♻️**

*   除了对 Mnemosyne 的贡献外，开发者 **Rail1bc** 还独立开发了一款名为 **“堆肥桶”** 的插件。
*   **主要功能**：这款插件同样致力于提升 DeepSeek API 的缓存利用效率，即使您不喜欢使用Mnemosyne插件带来的功能，仍可以使用堆肥桶作为一个增强工具来进一步优化缓存命中表现。（堆肥桶并不会带来过多的体验上的改变）
*   **项目地址**：感兴趣的用户可以通过以下链接访问并了解详情：🔗 [astrbot_plugin_composting_bucket](https://github.com/Rail1bc/astrbot_plugin_composting_bucket)

如果您是 DeepSeek API 的用户，并且希望更经济高效地使用服务，强烈建议尝试这款由 **Rail1bc** 带来的优秀工具。

---
### API获取

> 这里推荐一个平台：[阿里云百炼](https://bailian.console.aliyun.com/)
>
> 登录后可以在模型广场获得各种类型的模型，包括该插件所需要的embedding模型
>
> 此外阿里不定期新推出的大模型在该平台也有免费额度可以使用


> **⚠️ 警告：** 在配置中设置向量维度应与向量模型输出的维度相同。当换用别的向量模型后，切记注意是否与原向量模型输出维度相同，如果不相同，需要执行`/memory delete`指令删除之前的数据

---

## 📚 需要注意的地方
1.  版本稳定性
    
    当前插件为初版（v0.2.0），可能存在未预见的逻辑错误或性能问题，暂不建议直接部署于核心业务或高负载机器人。建议先在测试环境中验证稳定性。

2.  记忆总结机制
    
    ⏳ 阈值触发：需达到设定对话轮次才会触发长期记忆总结，初期需积累一定交互量才能生效。
    
    🗃️ 全量总结：现在设计了一个全量总结窗口，当窗口满时会自动对窗口中历史对话消息进行总结，不遗漏任何消息

3.  数据敏感性

    避免输入敏感信息，当前版本未内置数据脱敏机制，长期记忆存储可能涉及隐私风险。

---

## 更新日志

详见：[更新日志](docs/update_log.md)

## 🙏 致谢
- AstrBot核心开发团队的技术支持

如果本项目给您带来欢乐，欢迎点亮⭐️，您的支持是我不断前进的动力！

如果您有任何好的意见和想法，或者发现了bug，请随时提ISSUE，非常欢迎您的反馈和建议。我会认真阅读每一条反馈，并努力改进项目，提供更好的用户体验。

感谢您的支持与关注，期待与您共同进步！

## 🌟 贡献者

[![Contributors](https://img.shields.io/github/contributors/lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors)

<a href="https://github.com/lxfight/astrbot_plugin_mnemosyne/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=lxfight/astrbot_plugin_mnemosyne" />
</a>


感谢所有贡献者！  

**Star趋势**：  
[![Star History Chart](https://api.star-history.com/svg?repos=lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne)

_每一个star都是我们前进的动力！_

