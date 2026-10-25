# Performance and Tuning

Mnemosyne latency comes from embedding, vector search, post-processing, and prompt injection. The admin panel reports P50/P95/P99 for each stage using the latest 1,000 samples in the current process. Samples reset when the process restarts.

## Start With Stage Metrics

Use the performance panel to identify where latency accumulates:

- **Embedding**: time spent in the AstrBot Embedding Provider. Check network access and rate limits when it stays high.
- **Vector search**: ANN search time in the configured backend. Check index type, collection load state, and backend resources.
- **Post-processing**: participant filtering, keyword reranking, and lightweight graph expansion.
- **Injection**: formatting and appending memories to the request. This should normally be much cheaper than embedding and vector search.
- **Database operations**: memory insert/flush time. Flush is usually more expensive than insert.
- **Memory query**: total RAG retrieval time.

Warnings are emitted above these thresholds: embedding 500 ms, vector search 300 ms, post-processing 100 ms, injection 50 ms, database operation 500 ms, and total retrieval 1,000 ms.

## Retrieval Path and Candidate Count

Retrieval expands the candidate set only when the query contains rerankable keywords or participant filtering is enabled:

```text
candidate_limit = min(top_k * 4, 60)
```

Without keywords or participant filtering, `candidate_limit` is simply `top_k`, avoiding unnecessary vector search output and post-processing work. The backend returns candidates, then Mnemosyne applies participant filtering, keyword reranking, optional lightweight graph expansion, and finally injects the top `top_k` results. Lowering `top_k` reduces vector search output, post-processing CPU, and prompt size at the same time.

## Tuning Options

| Option | Impact | Guidance |
| --- | --- | --- |
| `top_k` | Candidates, post-processing, injected length | Start with 3-5; do not raise it blindly on latency-sensitive deployments |
| `memory_injection_interval` | Retrieval frequency | Use 2-5 for high-volume conversations to avoid repeated retrieval |
| `use_lightweight_memory_graph` | One-hop expansion and reranking | Disable when relationship expansion is unnecessary |
| `use_participant_filtering` | Group-chat participant filtering | Enable only when group memories visibly bleed across participants |
| `use_session_filtering` | Retrieval scope | Disabling it expands the search pool and usually increases latency |

## Vector Database

- At startup, Mnemosyne adds `INVERTED` scalar indexes for Milvus `session_id`, `personality_id`, and `create_time`, and creates matching `keyword`/`integer` payload indexes for Qdrant.
- Milvus `AUTOINDEX` does not use `nprobe`; Mnemosyne no longer sends it by default.
- `IVF_FLAT`, `IVF_SQ8`, and `IVF_PQ` default to `nprobe=10`.
- `HNSW` defaults to `ef=64`.
- `DISKANN` defaults to `search_list=16`.

You can override `index_params` and `search_params`. The metric type in `search_params` must match the index metric.

## Admin Panel

Statistics, session lists, and resource statistics use a 10-second cache so dashboard refreshes do not repeatedly fetch up to 10,000 records. Deleting or updating a memory invalidates the relevant cache immediately.

Exports and global keyword searches keep a 10,000-record safety limit. That limit is not a page size. For large collections, filter by session or date instead of exporting everything repeatedly.

## Operational Notes

Vector search has a default 5-second timeout, but `asyncio.wait_for` cannot stop a Python worker thread. If searches keep timing out, inspect backend load and network health instead of increasing the timeout or `top_k` further.
