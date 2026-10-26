# Database Options

Mnemosyne now supports multiple vector database backends through one internal adapter interface: Chroma, Milvus, Qdrant, and Weaviate.

## Choosing a Backend

| Backend | Best for | Deployment cost | Notes |
| --- | --- | --- | --- |
| Chroma | Personal use, quick trials, local deployment | Lowest | Default backend, no extra service required |
| Milvus | Large vector datasets or existing Milvus clusters | Higher | Good fit for production clusters and high throughput |
| Qdrant | High-performance search with a simple server | Medium | Supports local path or remote service mode |
| Weaviate | Object model and broader vector database ecosystem | Medium to high | Supports embedded or service mode |

New users should start with Chroma. Move to another backend when scale, concurrency, or operational needs require it.

## Chroma

Chroma is the default backend:

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

If `persist_directory` is empty, Mnemosyne uses the default plugin data path. Setting `host` switches to Chroma HTTP client mode.

## Milvus

Milvus is suitable for existing Milvus deployments or larger datasets. Install the optional dependency first:

```bash
uv pip install 'pymilvus[milvus_lite]>=2.6.0,<3.0.0'
```

Milvus Lite example:

```json
{
  "vector_db_type": "milvus",
  "milvus_lite_path": "./data/milvus.db",
  "collection_name": "default",
  "db_name": "default"
}
```

Milvus Lite is not supported on Windows. Windows users who need Milvus should deploy Milvus Standalone and connect through `address`.

Standard Milvus example:

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

Qdrant supports local persistence and remote service mode. Install the optional dependency first:

```bash
uv pip install 'qdrant-client>=1.7.0,<2.0.0'
```

Local mode:

```json
{
  "vector_db_type": "qdrant",
  "qdrant_config": {
    "path": "",
    "distance": "Cosine"
  }
}
```

Server mode:

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

Weaviate is useful when you want an object model and richer vector database features. Install the optional dependency first:

```bash
uv pip install 'weaviate-client>=3.25.0,<4.0.0'
```

Embedded mode:

```json
{
  "vector_db_type": "weaviate",
  "weaviate_config": {
    "embedded": true,
    "persistence_data_path": ""
  }
}
```

Server mode:

```json
{
  "vector_db_type": "weaviate",
  "weaviate_config": {
    "url": "http://localhost:8080",
    "api_key": ""
  }
}
```

## Switching Backends

Records are not automatically migrated between different vector database backends. When switching:

1. Stop AstrBot.
2. Back up the old database data path.
3. Update `vector_db_type` and the matching backend config.
4. Start AstrBot.
5. Run `/memory init --force`.
6. Rebuild memories over time, or write a one-off migration script.

If you only change connection details for the same backend, back up first and run initialization checks afterward.
