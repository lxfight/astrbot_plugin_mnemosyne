# Commands and Admin

Mnemosyne provides `/memory` commands for initialization, inspection, manual writes, and cleanup. Destructive commands may require administrator permission and an explicit confirmation argument.

## Common Commands

| Command | Description |
| --- | --- |
| `/memory init [--force]` | Initialize or migrate the memory system. Required after first install. |
| `/memory list` | List memory collections. |
| `/memory list_records [collection] [limit]` | List records in a collection. |
| `/memory get_session_id` | Show the current session ID. |
| `/memory remember [content]` | Write one long-term memory manually. |
| `/memory reset [confirm]` | Clear memory for the current session. |
| `/memory delete_record [id] [session] [confirm]` | Delete a single memory record from a session. |
| `/memory delete_session_memory [id] [confirm]` | Delete all memories for a session. |
| `/memory delete_before [time] [session] [--confirm]` | Preview or delete memories created before a time. |
| `/memory delete_between [start] [end] [session] [--confirm]` | Preview or delete memories in a time range. |
| `/memory export [filename] [session\|--all] [start] [end]` | Export memories to a JSON file. |
| `/memory import [filename] [--confirm]` | Preview or import a Mnemosyne JSON export. |
| `/memory stats [session\|--all]` | Show memory count and time-range statistics. |
| `/memory search [keyword] [session\|--all] [limit]` | Search memory content by keyword. |
| `/memory drop_collection [name] [confirm]` | Drop an entire collection. |

## Initialization

After the first install, database switch, or Embedding model change, run:

```text
/memory init
```

If the collection schema needs to be rebuilt:

```text
/memory init --force
```

## Manual Memory Writes

When `enable_explicit_memory_capture` is enabled, natural language triggers can capture memories. You can also write one directly:

```text
/memory remember The user is working on the Mnemosyne VitePress documentation site.
```

## Deleting Data

Deletion commands generally require confirmation. Use `list_records` or the admin panel to verify record IDs first.

```text
/memory delete_record 123456 current_session confirm
```

To clear the current session:

```text
/memory reset confirm
```

## Time-based Cleanup and Import/Export

`delete_before` and `delete_between` show a preview first and delete only when `--confirm` is supplied. These commands, as well as export, import, statistics, and search, require AstrBot administrator permission.

```text
/memory delete_before 2026-07-01
/memory delete_before 2026-07-01 --confirm
/memory delete_between 2026-06-01 2026-07-01 --confirm
```

When no session ID is supplied, commands operate on the current session. Use `--all` only when exporting, viewing statistics, or searching every session. Export files are always stored in the plugin data directory under `exports`; importing regenerates embeddings and requires a preview followed by confirmation.

```text
/memory export july-memory.json
/memory export full-memory.json --all
/memory import july-memory.json
/memory import july-memory.json --confirm
/memory stats
/memory search preference
```

## Web Admin Panel

Open the long-term memory page under **Alkaid** in AstrBot Dashboard to:

- Inspect database connection status.
- Search and browse memory records.
- Delete individual records or session memories.
- View collection statistics.

The admin panel and command system share the same database adapter layer, so Chroma, Milvus, Qdrant, and Weaviate use the same management entry points.
