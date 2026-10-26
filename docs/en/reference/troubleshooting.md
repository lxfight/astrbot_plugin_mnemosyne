# Troubleshooting

## Embedding Provider Not Found

Check AstrBot provider settings and make sure at least one Embedding Provider is available. Mnemosyne needs embeddings to convert text into vectors.

## Memories Are Not Summarized

Common causes:

- The conversation has not reached `num_pairs`.
- The LLM Provider is missing or failing.
- The platform is listed in `platform_blacklist`.
- The current session does not contain enough useful messages to summarize.

Temporarily lower `num_pairs` and inspect AstrBot logs for Mnemosyne messages.

## Retrieval Misses Relevant Memories

Check these settings:

- `top_k` may be too low.
- `use_lightweight_memory_graph` may not suit the entity distribution in the current data.
- `use_session_filtering` may limit retrieval to the current session.
- `use_personality_filtering` may exclude memories from a different persona.
- The Embedding model may have changed without reinitializing the collection.

## Where Is Chroma Data Stored

If `chroma_config.persist_directory` is empty, Mnemosyne creates a Chroma persistence directory under the default plugin data path. Stop AstrBot before copying that directory to another machine.

## Milvus Connection Fails

Check `address`, `db_name`, and authentication settings. For standard Milvus, confirm the service port is reachable:

```bash
nc -vz localhost 19530
```

For Milvus Lite, make sure `milvus_lite_path` points to a writable path.

If the log contains `No module named 'pkg_resources'`, an outdated Milvus Lite build is relying on legacy setuptools behavior. Do not downgrade AstrBot's setuptools; upgrade the optional dependency instead:

```bash
uv pip install --upgrade 'pymilvus[milvus_lite]>=2.6.0,<3.0.0'
```

New Milvus collections use a `session_id` field length of 500. For existing standard Milvus collections, Mnemosyne attempts to expand the old 72-character field online at startup; if the server cannot alter it, upgrade PyMilvus and Milvus and reload the plugin. Milvus Lite does not currently support online field alteration, so use a new collection name or export the old collection and migrate it into a new one. Mnemosyne never drops or rebuilds existing collections automatically.

## Memories Disappear After Switching Databases

Different vector backends do not share data automatically. After switching, initialize the new backend and rebuild memories over time, or export records from the old backend and import them into the new one.
