---
layout: home

hero:
  name: Mnemosyne
  text: Long-term memory for AstrBot
  tagline: A searchable and manageable memory layer for AstrBot. Chroma is the default backend, so local persistence works without running a separate database service.
  image:
    src: /mnemosyne-mark.svg
    alt: Mnemosyne
  actions:
    - theme: brand
      text: Get Started
      link: /en/guide/getting-started
    - theme: alt
      text: Choose a Database
      link: /en/guide/database

features:
  - title: Chroma by default
    details: New installations use local Chroma persistence, which keeps the first-run path simple.
  - title: Multiple vector backends
    details: Chroma, Milvus, Qdrant, and Weaviate share one adapter interface inside the plugin.
  - title: Native AstrBot integration
    details: The plugin uses AstrBot LLM and Embedding providers for summarization, vectorization, retrieval, and memory injection.
  - title: Session and persona filters
    details: Keep memories scoped by session, persona, participant, or platform to reduce cross-chat leakage.
  - title: Web admin panel
    details: Browse, search, delete, and inspect memory records from the AstrBot Dashboard.
  - title: Operational commands
    details: Initialize collections, write explicit memories, delete records, and maintain collections with `/memory`.
---

## Start Here

- First install: read [Getting Started](/en/guide/getting-started).
- Configuration details: read [Configuration](/en/guide/configuration).
- Backend selection: read [Database Options](/en/guide/database).
- Daily operations: read [Admin Panel](/en/guide/admin-panel) and [Commands](/en/guide/commands).
- Implementation details: read [Architecture](/en/reference/architecture).
- Contributing: read [Development and Deployment](/en/reference/development).

中文文档位于 [/](/).
