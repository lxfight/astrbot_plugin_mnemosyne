"""总结记忆写入语义测试。"""

import pytest

from core.memory_operations import _store_summary_to_vector_db
from memory_manager.vector_db_base import VectorInsertResult


class _FlushFailingVectorDB:
    def insert(self, **_kwargs):
        return VectorInsertResult(insert_count=1, primary_keys=["1"])

    def flush(self, _collection_names):
        raise RuntimeError("flush unavailable")


class _FlushReturningFalseVectorDB(_FlushFailingVectorDB):
    def flush(self, _collection_names):
        return False


class _InsertFailingVectorDB:
    def insert(self, **_kwargs):
        return VectorInsertResult(insert_count=0, primary_keys=[])


def _plugin(vector_db):
    return type(
        "_Plugin",
        (),
        {
            "collection_name": "memory_collection",
            "config": {},
            "vector_db": vector_db,
            "metrics_collector": None,
        },
    )()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vector_db",
    [_FlushFailingVectorDB(), _FlushReturningFalseVectorDB()],
)
async def test_insert_success_is_not_reported_as_failure_when_flush_fails(vector_db):
    stored = await _store_summary_to_vector_db(
        _plugin(vector_db),
        persona_id=None,
        session_id="session-1",
        summary_text="summary",
        embedding_vector=[0.1, 0.2],
    )

    assert stored is True


@pytest.mark.asyncio
async def test_insert_failure_is_reported():
    stored = await _store_summary_to_vector_db(
        _plugin(_InsertFailingVectorDB()),
        persona_id=None,
        session_id="session-1",
        summary_text="summary",
        embedding_vector=[0.1, 0.2],
    )

    assert stored is False
