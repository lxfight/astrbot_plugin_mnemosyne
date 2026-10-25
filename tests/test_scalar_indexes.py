from types import SimpleNamespace

from astrbot_plugin_mnemosyne.core import initialization
from memory_manager.vector_db.qdrant_adapter import QdrantVectorDB


class _IndexClient:
    def __init__(self):
        self.created = []

    def create_payload_index(self, **kwargs):
        self.created.append(kwargs)


def test_qdrant_creates_indexes_for_filter_fields():
    adapter = QdrantVectorDB()
    adapter._is_connected = True
    adapter._client = _IndexClient()

    adapter.ensure_payload_indexes("memory_collection")

    assert [
        (call["field_name"], call["field_schema"]) for call in adapter._client.created
    ] == [
        ("session_id", "keyword"),
        ("personality_id", "keyword"),
        ("create_time", "integer"),
    ]
    assert all(
        call["collection_name"] == "memory_collection" and call["wait"] is True
        for call in adapter._client.created
    )


def test_setup_ensures_qdrant_payload_indexes_for_existing_collection():
    class _VectorDB:
        def __init__(self):
            self.ensured = []

        def is_connected(self):
            return True

        def list_collections(self):
            return ["memory_collection"]

        def ensure_payload_indexes(self, collection_name):
            self.ensured.append(collection_name)

    plugin = SimpleNamespace(
        vector_db=_VectorDB(),
        collection_name="memory_collection",
        collection_schema_dict={"fields": []},
        config={"vector_db_type": "qdrant"},
    )

    initialization.setup_vector_db_collection_and_index(plugin)

    assert plugin.vector_db.ensured == ["memory_collection"]


def test_milvus_creates_inverted_scalar_indexes():
    class _Manager:
        def __init__(self):
            self.created = []
            self.collection = SimpleNamespace(
                indexes=[SimpleNamespace(field_name="embedding")]
            )

        def has_collection(self, _collection_name):
            return True

        def get_collection(self, _collection_name):
            return self.collection

        def create_index(self, **kwargs):
            self.created.append(kwargs)
            return True

    manager = _Manager()
    plugin = SimpleNamespace(
        config={"create_index_timeout": 120},
        index_params={"index_type": "AUTOINDEX", "metric_type": "L2", "params": {}},
        milvus_manager=manager,
    )

    initialization.ensure_milvus_index(plugin, "memory_collection")

    assert [call["field_name"] for call in manager.created] == [
        "session_id",
        "personality_id",
        "create_time",
    ]
    assert all(call["index_params"] == {"index_type": "INVERTED"} for call in manager.created)
    assert all(call["timeout"] == 120 for call in manager.created)
