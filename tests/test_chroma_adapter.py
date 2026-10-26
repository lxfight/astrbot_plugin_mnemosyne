"""
Chroma 适配器单元测试
"""

from unittest.mock import MagicMock, patch

import pytest


class TestChromaVectorDB:
    """测试 ChromaVectorDB 适配器"""

    @pytest.fixture
    def mock_chromadb(self):
        """Mock chromadb 模块"""
        settings = MagicMock()
        settings.anonymized_telemetry = False
        with (
            patch("memory_manager.vector_db.chroma_adapter.chromadb") as mock,
            patch(
                "memory_manager.vector_db.chroma_adapter._chroma_settings",
                return_value=settings,
            ),
        ):
            yield mock

    @pytest.fixture
    def chroma_db(self, mock_chromadb):
        """创建 ChromaVectorDB 实例"""
        from memory_manager.vector_db.chroma_adapter import ChromaVectorDB

        db = ChromaVectorDB(persist_directory="./test_data/chroma")
        return db

    def test_init_local_mode(self):
        """测试本地持久化模式初始化"""
        from memory_manager.vector_db.chroma_adapter import ChromaVectorDB

        db = ChromaVectorDB(persist_directory="./test_data/chroma")

        assert db._persist_directory == "./test_data/chroma"
        assert db._host is None
        assert db._port is None
        assert not db._is_connected

    def test_init_client_mode(self):
        """测试客户端模式初始化"""
        from memory_manager.vector_db.chroma_adapter import ChromaVectorDB

        db = ChromaVectorDB(host="localhost", port=8000)

        assert db._host == "localhost"
        assert db._port == 8000
        assert db._persist_directory is None

    def test_connect_local_mode(self, chroma_db, mock_chromadb):
        """测试本地模式连接"""
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        chroma_db.connect()

        assert chroma_db._is_connected
        assert chroma_db._client == mock_client
        mock_chromadb.PersistentClient.assert_called_once()

    def test_connect_client_mode(self, mock_chromadb):
        """测试客户端模式连接"""
        from memory_manager.vector_db.chroma_adapter import ChromaVectorDB

        db = ChromaVectorDB(host="localhost", port=8000)
        mock_client = MagicMock()
        mock_chromadb.HttpClient.return_value = mock_client

        db.connect()

        assert db._is_connected
        assert db._client == mock_client
        mock_chromadb.HttpClient.assert_called_once()
        call_args = mock_chromadb.HttpClient.call_args[1]
        assert call_args["host"] == "localhost"
        assert call_args["port"] == 8000
        assert call_args["settings"].anonymized_telemetry is False

    def test_create_collection(self, chroma_db, mock_chromadb):
        """测试创建集合"""
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        schema = {"fields": []}  # 简化的 schema
        chroma_db.create_collection("test_collection", schema)

        mock_client.get_or_create_collection.assert_called_once_with(
            name="test_collection",
            metadata={"hnsw:space": "l2"}
        )

    def test_insert_data(self, chroma_db):
        """测试插入数据"""
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        data = [
            {
                "embedding": [0.1, 0.2, 0.3],
                "content": "测试内容",
                "personality_id": "test_persona",
                "session_id": "test_session",
                "create_time": 1234567890
            }
        ]

        chroma_db.insert("test_collection", data)

        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args[1]

        assert len(call_args["ids"]) == 1
        assert len(call_args["embeddings"]) == 1
        assert len(call_args["documents"]) == 1
        assert len(call_args["metadatas"]) == 1
        assert call_args["documents"][0] == "测试内容"

    def test_search(self, chroma_db):
        """测试向量搜索"""
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        # Mock 搜索结果
        mock_collection.query.return_value = {
            "ids": [["id1", "id2"]],
            "documents": [["doc1", "doc2"]],
            "distances": [[0.1, 0.2]],
            "metadatas": [[
                {"personality_id": "p1", "session_id": "s1"},
                {"personality_id": "p2", "session_id": "s2"}
            ]]
        }

        query_vector = [0.1, 0.2, 0.3]
        results = chroma_db.search("test_collection", query_vector, top_k=2)

        assert len(results) == 2
        assert results[0]["id"] == "id1"
        assert results[0]["distance"] == 0.1
        assert "score" in results[0]
        assert results[0]["personality_id"] == "p1"

    def test_list_collections(self, chroma_db):
        """测试列出集合"""
        mock_client = MagicMock()
        mock_collection1 = MagicMock()
        mock_collection1.name = "collection1"
        mock_collection2 = MagicMock()
        mock_collection2.name = "collection2"

        mock_client.list_collections.return_value = [mock_collection1, mock_collection2]
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        collections = chroma_db.list_collections()

        assert collections == ["collection1", "collection2"]

    def test_list_collections_chroma_06_strings(self, chroma_db):
        """测试 Chroma 0.6 返回字符串集合名称。"""
        mock_client = MagicMock()
        mock_client.list_collections.return_value = ["collection1", "collection2"]
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        collections = chroma_db.list_collections()

        assert collections == ["collection1", "collection2"]

    def test_delete(self, chroma_db):
        """测试删除数据"""
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        # Mock get 返回要删除的 ID
        mock_collection.get.return_value = {
            "ids": ["id1", "id2"]
        }

        chroma_db.delete("test_collection", "session_id == 'test_session'")

        mock_collection.delete.assert_called_once_with(ids=["id1", "id2"])

    def test_drop_collection(self, chroma_db):
        """测试删除集合"""
        mock_client = MagicMock()
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        chroma_db.drop_collection("test_collection")

        mock_client.delete_collection.assert_called_once_with(
            name="test_collection"
        )

    def test_count_uses_native_count_without_filters(self, chroma_db):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 42
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        assert chroma_db.count("test_collection") == 42

        mock_collection.count.assert_called_once_with()
        mock_collection.get.assert_not_called()

    def test_count_only_fetches_matching_ids_with_filters(self, chroma_db):
        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["id1", "id2", "id3"]}
        mock_client = MagicMock()
        mock_client.get_collection.return_value = mock_collection
        chroma_db._client = mock_client
        chroma_db._is_connected = True

        count = chroma_db.count(
            "test_collection", "session_id == 'test_session'"
        )

        assert count == 3
        mock_collection.get.assert_called_once_with(
            include=[],
            where={"session_id": {"$eq": "test_session"}},
        )

    def test_parse_filters_simple(self, chroma_db):
        """测试简单过滤条件解析"""
        filters = "session_id == 'test_session'"
        where = chroma_db._parse_filters(filters)

        assert where == {"session_id": {"$eq": "test_session"}}

    def test_parse_filters_empty(self, chroma_db):
        """测试空过滤条件"""
        where = chroma_db._parse_filters("")
        assert where is None

        where = chroma_db._parse_filters(None)
        assert where is None

    def test_ensure_connected_reconnect(self, chroma_db, mock_chromadb):
        """测试自动重连"""
        chroma_db._is_connected = False
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        chroma_db._ensure_connected()

        assert chroma_db._is_connected
        assert chroma_db._client == mock_client

    def test_context_manager(self, mock_chromadb):
        """测试上下文管理器"""
        from memory_manager.vector_db.chroma_adapter import ChromaVectorDB

        db = ChromaVectorDB(persist_directory="./test_data")
        mock_client = MagicMock()
        mock_chromadb.PersistentClient.return_value = mock_client

        with db:
            assert db._is_connected

        # 退出后连接应该关闭
        assert not db._is_connected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
