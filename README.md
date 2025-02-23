# 🧠 Mnemosyne - AstrBot的长期记忆中枢

> "记忆造就了我们的存在" —— 神经科学家Eric Kandel
> 
> 让AI真正记住与你的每一次对话

## 🌟 核心能力

### 🗃️ 对话记忆提炼
- 自动从聊天历史中提取关键信息
- 智能总结对话要点

### 🔢 记忆向量化
- 支持OpenAI兼容的向量模型接口
- 动态维度映射（384/512/768维灵活配置）

### 🚀 Milvus记忆库
- 分布式向量检索（支持千万级记忆存储）
- 混合索引方案（HNSW + IVF）
- 毫秒级记忆召回（平均响应时间<150ms）
> 作者的话：Milvus真的好厉害

## 🛠️ 快速接入指南

### 环境配置
注意，本插件需要有额外环境配置：`pypinyin`和`pymilvus`

```bash
pip install pypinyin pymilvus
```

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



## 📚 需要注意的地方
1.  版本稳定性
    
    当前插件为初版（v0.2.0），可能存在未预见的逻辑错误或性能问题，暂不建议直接部署于核心业务或高负载机器人。建议先在测试环境中验证稳定性。
2.  记忆总结机制
    
    ⏳ 阈值触发：需达到设定对话轮次才会触发长期记忆总结，初期需积累一定交互量才能生效。
    
    🗃️ 全量总结：现在设计了一个全量总结窗口，当窗口满时会自动对窗口中历史对话消息进行总结，不遗漏任何消息

3.  数据敏感性

    避免输入敏感信息，当前版本未内置数据脱敏机制，长期记忆存储可能涉及隐私风险。


## 更新日志

详见：[更新日志](docs/update_log.md)

## 🙏 致谢
- AstrBot核心开发团队的技术支持

如果本项目给您带来欢乐，欢迎点亮⭐️，您的支持是我不断前进的动力！

如果您有任何好的意见和想法，或者发现了bug，请随时提ISSUE，非常欢迎您的反馈和建议。我会认真阅读每一条反馈，并努力改进项目，提供更好的用户体验。

感谢您的支持与关注，期待与您共同进步！

**Star趋势**：  
[![Star History Chart](https://api.star-history.com/svg?repos=lxfight/astrbot_plugin_mnemosyne)](https://github.com/lxfight/astrbot_plugin_mnemosyne)
_每一个star都是我们前进的动力！_
