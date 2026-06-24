"""Integration tests — OpenSearch backend against sandbox-db."""
import pytest

INSTANCE = "sandbox-opensearch"
pytestmark = pytest.mark.asyncio


async def test_health_check(registry):
    b = await registry.get(INSTANCE)
    h = await b.health_check()
    assert h["status"] == "ok"
    assert "version" in h


async def test_cluster_health(registry):
    b = await registry.get(INSTANCE)
    health = await b.cluster_health()
    assert health["status"] in ("green", "yellow", "red")


async def test_schema_inspect_indices(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "indices" in result


async def test_indices_stats(registry):
    b = await registry.get(INSTANCE)
    result = await b.indices_stats()
    assert isinstance(result, list)


async def test_shard_allocation(registry):
    b = await registry.get(INSTANCE)
    result = await b.shard_allocation()
    assert isinstance(result, list)


async def test_db_stats(registry):
    b = await registry.get(INSTANCE)
    stats = await b.db_stats()
    assert "indices_count" in stats


async def test_pending_tasks(registry):
    b = await registry.get(INSTANCE)
    result = await b.pending_tasks()
    assert isinstance(result, list)
