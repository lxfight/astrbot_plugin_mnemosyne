# 🧠 Mnemosyne - AstrBot的长期记忆中枢

> "记忆造就了我们的存在" —— 神经科学家Eric Kandel
> 
> 让AI真正记住与你的每一次对话

---

## 相关支持与讨论

如您需要更及时的关于本插件使用的帮助，可以加入群聊：`953245617`与开发者和其他用户进一步讨论

---

- ## 小更新速览
    - ### v0.2.7
        - [#23](https://github.com/lxfight/astrbot_plugin_mnemosyne/issues/23)问题修复

    - ### v0.2.6
        - 在插件初始化时，增加了相关错误的捕捉和提示，解决插件安装后初始化失败带来的问题。

    - ### v0.2.5
        - 添加了两条指令支持：`/memory delete_session_memory`和`/memory get_session_id`实现会话级别的记忆删除
---

- ## 开发分支更新介绍
    - ### v0.3.1
        - **更进一步的代码结构整理**: 优化了代码结构，提升插件的可维护性和扩展性。
        - **main.py代码更加简洁**: 改进代码结构，使逻辑更清晰，易于理解。

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

感谢所有贡献者！  

**Star趋势**：  
[![Star History Chart](https://api.star-history.com/svg?repos=lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne)

_每一个star都是我们前进的动力！_

