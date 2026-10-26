# Configuration

Mnemosyne configuration is grouped around model providers, vector databases, memory behavior, and administration. The smallest working setup keeps Chroma as the default backend and selects LLM and Embedding providers.

## Model Providers

| Option | Description | Default |
| --- | --- | --- |
| `LLM_providers` | LLM Provider used to summarize conversations. Empty means the current session default provider is used. | Empty |
| `embedding_provider_id` | Embedding Provider used to generate vectors. Empty means the first available AstrBot Embedding Provider is used. | Empty |
| `summary_request_timeout_seconds` | Timeout for a summarization request. A timeout cancels the request and tries the fallback provider. | `60` |
| `embedding_request_timeout_seconds` | Timeout for an Embedding request. A timeout cancels the request. | `15` |

The Embedding Provider dimension defines the collection schema. After changing embedding models, run `/memory init --force` to check or rebuild the collection.

## Vector Database

| Option | Description | Default |
| --- | --- | --- |
| `vector_db_type` | Vector backend: `chroma`, `milvus`, `qdrant`, or `weaviate`. | `chroma` |
| `collection_name` | Collection used for long-term memory records. | `default` |
| `chroma_config.persist_directory` | Chroma local persistence path. Empty uses the plugin data path. | Empty |
| `chroma_config.host` | Chroma HTTP server host. Empty uses local persistent mode. | Empty |
| `qdrant_config.path` | Qdrant local persistence path. | Empty |
| `qdrant_config.url` | Qdrant server URL. | Empty |
| `weaviate_config.embedded` | Whether to run Weaviate embedded mode. | `false` |
| `milvus_lite_path` | Milvus Lite database file path. | Empty |
| `address` | Standard Milvus server address. | Empty |
| `db_name` | Milvus database name. | `default` |

See [Database Options](/en/guide/database) for backend guidance.

## Memory Behavior

| Option | Description | Default |
| --- | --- | --- |
| `num_pairs` | Conversation rounds required before automatic summarization. | `5` |
| `context_cache_max_sessions` | Maximum active sessions kept in memory; the least recently used session is evicted first. | `2048` |
| `context_cache_idle_ttl_seconds` | Idle time before a session is released; `0` disables time-based eviction. | `604800` |
| `context_cache_max_messages` | Maximum messages kept per session; older messages are dropped first. | `200` |
| `top_k` | Number of memories returned by retrieval. | `3` |
| `contexts_memory_len` | Number of long-term memory tag blocks retained in context. Values below 0 keep all blocks; 0 removes all. | `0` |
| `memory_injection_method` | `extra_user_parts` appends memory as a temporary content block on the current user message; `user_prompt` edits the user prompt; `system_prompt` edits the LLM system prompt; `insert_system_prompt` adds a separate system message. | `extra_user_parts` |
| `memory_injection_interval` | Retrieve and inject memories once every N conversation turns. | `1` |
| `memory_injection_position` | Place `user_prompt`, `system_prompt`, or `insert_system_prompt` content before or after the active prompt. | `prepend` |
| `max_prompt_chars_for_embedding` | Maximum input characters before embedding; longer text is truncated. | `4000` |
| `summary_max_concurrency` | Maximum number of summarization tasks running at the same time. | `2` |
| `summary_fallback_provider_id` | Retry with this provider when the primary summarizer fails or returns empty text. | Empty |
| `summary_speaker_mapping_prompt` | Constrain `user`, `assistant`, and first-person ownership with session and speaker variables. | Built-in mapping |
| `enable_llm_memory_tool` | Let tool-capable models write to the current session through `mnemosyne_remember_memory`. When disabled, calls return without writing. | `true` |

If memories become too noisy, lower `top_k`, increase `memory_injection_interval`, or disable lightweight graph reranking.

The default `extra_user_parts` mode appends memory as a temporary `TextPart` on the current user message. It is not written to conversation history and does not trigger history cleanup. `memory_injection_position` does not affect this mode: the block is always appended after the current user message.

`memory_injection_position` only controls `user_prompt`, `system_prompt`, and `insert_system_prompt`. `insert_system_prompt` creates a separate system message and may reduce prompt-cache hits on some models; prefer `extra_user_parts` when cache stability matters.

## Filters

| Option | Description | Default |
| --- | --- | --- |
| `use_session_filtering` | Keep memories isolated by session. Disable to share one global memory pool. | `true` |
| `use_personality_filtering` | Filter memories by persona. | `true` |
| `use_participant_filtering` | Prefer memories related to the current speaker in group chats. | `false` |
| `platform_blacklist` | Platform IDs where long-term memory is disabled. | `[]` |

Session isolation is safer for multi-user or group-chat deployments. Global memory works well for single-user assistants or shared knowledge bases.

## Lightweight Graph Rerank

When `use_lightweight_memory_graph` is enabled, Mnemosyne extracts lightweight entity relations from memories and uses one-hop expansion during reranking. This helps with long-running contexts such as preferences, project state, and relationship-like facts.

Disable it if you prefer the simplest behavior or want to optimize retrieval latency first.
