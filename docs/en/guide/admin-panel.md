# Admin Panel

Mnemosyne exposes its long-term memory management pages through AstrBot Dashboard. The panel uses the same vector database adapters as the plugin, so Chroma, Milvus, Qdrant, and Weaviate share one management entry point.

## Open the Panel

1. Sign in to Dashboard with an AstrBot administrator account.
2. Open **Alkaid**.
3. Select **Long-term Memory**.

Menu labels can differ slightly between AstrBot releases, but the pages stay inside the plugin management area. The panel does not listen on a separate port or maintain its own account system.

## Pages

| Page | Purpose |
| --- | --- |
| System Pulse | Review system state, memory count, active sessions, database health, and the memory topology. |
| Memory Workbench | Search by session, persona, date, or keyword; inspect records and delete entries. |
| Session Map | Review memory counts and time ranges per session, and clear an entire session. |
| Statistics | Inspect daily growth, session distribution, and total-memory trends. |
| Runtime Configuration | Verify the active database, model, and retrieval settings. |

## Editing Memories

The memory inspector accepts edits to the memory body. Saving regenerates the Embedding before writing the record back to the vector database.

- Memory content is limited to 4096 characters, matching the collection field.
- Content changes affect future retrieval, so do not treat an edit as a cosmetic correction.
- Record, session, and batch deletions ask for confirmation inside the page and cannot be undone.

## Performance Metrics

The panel reports staged latency for Embedding, vector search, post-processing, injection, database operations, and the complete RAG query. Each metric includes P50, P95, and P99.

Metrics stay in the current process, retain up to 1,000 samples, and reset when AstrBot restarts. Compare P95 values first, then tune the provider, database, or retrieval settings. See [Performance](/en/guide/performance) for thresholds and tuning guidance.

## Cache and Refresh

Memory statistics, session lists, and resource usage use a 10-second cache so dashboard refreshes do not scan the same records repeatedly. Deleting or updating a memory invalidates the relevant cache immediately.

## Security

- The panel inherits AstrBot administrator permissions. Do not expose Dashboard anonymously to the public internet.
- Memory content can contain personal preferences, conversation fragments, and business information. Treat exports as sensitive data.
- Deletion is irreversible. Preview cleanup commands or export a backup before bulk changes.
