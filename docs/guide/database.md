# 数据库选择

Mnemosyne 已完成多数据库改造。插件内部通过统一接口访问向量数据库，目前支持 Chroma、Milvus、Qdrant 和 Weaviate。

## 如何选择

| 后端 | 推荐场景 | 部署成本 | 备注 |
| --- | --- | --- | --- |
| Chroma | 个人使用、快速试用、本地部署 | 最低 | 默认选择，无需额外服务 |
| Milvus | 大规模向量数据、已有 Milvus 集群 | 较高 | 适合生产集群和高吞吐场景 |
| Qdrant | 需要高性能检索和简洁服务端 | 中等 | 支持本地路径或远端服务 |
| Weaviate | 需要完整对象模型和丰富生态 | 中等到较高 | 可使用嵌入式或服务端模式 |

新用户建议先使用 Chroma。只有当数据规模、并发或运维要求变高时，再迁移到其他数据库。

## Chroma

Chroma 是默认后端。最小配置如下：

```json
{
  "vector_db_type": "chroma",
  "chroma_config": {
    "persist_directory": "",
    "host": "",
    "port": 8000
  }
}
```

`persist_directory` 留空时，插件会使用默认数据目录。填写 `host` 后会切换到 Chroma HTTP 客户端模式。

## Milvus

Milvus 适合已有 Milvus 服务或数据规模较大的部署。启用前需要安装可选依赖：

```bash
uv pip install 'pymilvus[milvus_lite]>=2.6.0,<3.0.0'
```

本地 Milvus Lite 示例：

```json
{
  "vector_db_type": "milvus",
  "milvus_lite_path": "./data/milvus.db",
  "collection_name": "default",
  "db_name": "default"
}
```

Milvus Lite 不支持 Windows。Windows 用户需要 Milvus 时，请部署 Milvus Standalone 并改用 `address` 连接。

标准 Milvus 示例：

```json
{
  "vector_db_type": "milvus",
  "address": "localhost:19530",
  "db_name": "default",
  "authentication": {
    "token": ""
  }
}
```

## Qdrant

Qdrant 支持本地持久化路径和远端服务模式。启用前安装可选依赖：

```bash
uv pip install 'qdrant-client>=1.7.0,<2.0.0'
```

本地模式：

```json
{
  "vector_db_type": "qdrant",
  "qdrant_config": {
    "path": "",
    "distance": "Cosine"
  }
}
```

服务端模式：

```json
{
  "vector_db_type": "qdrant",
  "qdrant_config": {
    "url": "http://localhost:6333",
    "api_key": "",
    "distance": "Cosine"
  }
}
```

## Weaviate

Weaviate 适合需要对象模型和丰富查询能力的场景。启用前安装可选依赖：

```bash
uv pip install 'weaviate-client>=3.25.0,<4.0.0'
```

嵌入式模式：

```json
{
  "vector_db_type": "weaviate",
  "weaviate_config": {
    "embedded": true,
    "persistence_data_path": ""
  }
}
```

服务端模式：

```json
{
  "vector_db_type": "weaviate",
  "weaviate_config": {
    "url": "http://localhost:8080",
    "api_key": ""
  }
}
```

## 切换数据库

不同数据库之间不会自动迁移既有向量数据。切换后建议：

1. 停止 AstrBot。
2. 备份旧数据库数据目录。
3. 修改 `vector_db_type` 和对应配置。
4. 启动 AstrBot。
5. 执行 `/memory init --force`。
6. 重新积累记忆，或编写一次性脚本迁移旧记录。

如果只是更换同一数据库的连接地址，也建议先备份，再执行初始化检查。
