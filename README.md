# 🧠 Mnemosyne - AstrBot的长期记忆中枢

> "记忆造就了我们的存在" —— 神经科学家Eric Kandel
> 
> 让AI真正记住与你的每一次对话

---

## 相关支持与讨论

如您需要更及时的关于本插件使用的帮助，可以加入群聊：`953245617`与开发者和其他用户进一步讨论

---

- ## 更新速览
    - ### v0.3.4 -> v0.3.7
        - **紧急修复**：增加对 astrbot_max_context_length 大小的判断，避免负数导致的错误
        - **恢复配置项功能**：恢复了配置项`历史上下文中保留的长期记忆数量 (contexts_memory_len)`的作用。
        - **修复`num_pairs`不生效的错误**：修复了关于`num_pairs`配置项无法生效，导致记忆总结时，携带大量历史记录。
        - **修复BUG**：关于`v0.3.3`版本以来，调用LLM总结记忆时，会有旧的记忆存在于上下文中，此版本进行了删除，以解决一些问题。
        - **修复指令BUG**：关于`/memory list_records` 指令错误的修复        
    - ### v0.3.3
        - **重构优化**：核心模块重构，提升代码质量与可维护性。
        - **记忆增强**：新增记忆注入方式配置 (`memory_injection_method`)，优化记忆处理逻辑。
        - **Milvus扩展**：支持 Milvus 数据库认证，并优化连接参数处理。
        - **配置检查**：增加启动时的配置兼容性检查。
        - **注意**: 本次更新使得原有的配置项`历史上下文中保留的长期记忆数量 (contexts_memory_len)`将不再生效。~~（已在AstrBot中实现，未来的版本本插件可能将该配置移除）~~


---

- ## 开发分支更新介绍
    - ### v0.3.0
        - **核心重构与优化：** 本次更新对 Milvus 数据库的控制逻辑进行了重写，并同步优化了长期记忆的存储机制。
            - **重要提示：** 由于涉及底层重构，新实现的稳定性尚未经过充分验证，建议您在评估风险后谨慎使用。
        - **连接性扩展：** 扩展了 Milvus 数据库的连接选项，在设计上增加了对通过代理地址进行连接的支持。
            - **注意：** 该代理连接功能目前仅停留在设计阶段，尚未经过实际测试或验证。

> **开发分支说明：** 未来所有关于 Mnemosyne 的新功能和更新将首先在开发分支（develop Branch）发布。只有当这些更新达到相对稳定的状态后，才会被合并到主分支（Main Branch）。

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

