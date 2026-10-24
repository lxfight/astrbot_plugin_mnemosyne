# Getting Started

This guide is for first-time Mnemosyne installations. The default backend is now Chroma, using local persistence without requiring a Milvus, Qdrant, or Weaviate service.

## Prerequisites

- AstrBot v4.0.0 or later
- Python 3.8 or later
- At least one LLM Provider configured in AstrBot
- At least one Embedding Provider configured in AstrBot

## Install Dependencies

Install plugin dependencies from the plugin directory:

```bash
cd data/plugins/astrbot_plugin_mnemosyne
uv pip install -r requirements.txt
```

The default dependency set includes Chroma. Milvus, Qdrant, and Weaviate are optional backends; enable their dependencies in `requirements.txt` only when you need them.

## Configure the Plugin

Open the plugin settings in AstrBot WebUI:

1. Go to **Plugin Management**.
2. Open **Mnemosyne**.
3. Keep **Vector database type** as `chroma`.
4. Select the LLM Provider used for memory summaries.
5. Select the Embedding Provider used for vectorization.
6. Adjust summary rounds, result count, and score threshold as needed.

You can leave Chroma `persist_directory` empty. Mnemosyne will create a default persistent directory under the plugin data path.

## Initialize

Run the initialization command as an administrator after the first install:

```text
/memory init
```

When changing the Embedding dimension, rebuilding collections, or migrating from an older version, run:

```text
/memory init --force
```

## Verify

Chat with the bot until the configured summary round count is reached. The AstrBot logs should show Mnemosyne summary and write activity.

You can also write a memory manually:

```text
/memory remember I prefer organizing project documentation at night.
```

Then ask a related question and check whether the bot retrieves and injects the memory.

## Admin Panel

Open AstrBot Dashboard and enter the long-term memory page under **Alkaid** to inspect memory records, connection status, and basic statistics.

## Next Steps

- Read [Configuration](/en/guide/configuration) for core options.
- Read [Database Options](/en/guide/database) before switching to Milvus, Qdrant, or Weaviate.
- Read [Admin Panel](/en/guide/admin-panel) to inspect, edit, and delete memories.
- Read [Commands and Admin](/en/guide/commands) for routine operations.
- Read [Architecture](/en/reference/architecture) to understand the write and retrieval paths.
