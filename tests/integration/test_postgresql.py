"""Integration tests — PostgreSQL backend against sandbox-db."""
import pytest

INSTANCE = "sandbox-postgres"
pytestmark = pytest.mark.asyncio


async def test_health_check(registry):
    result = await registry.get(INSTANCE)
    h = await result.health_check()
    assert h["status"] == "ok"
    assert "version" in h
    assert h["connection_count"] >= 1


async def test_query_select(registry):
    b = await registry.get(INSTANCE)
    rows = await b.query("SELECT 1 AS n")
    assert rows == [{"n": 1}]


async def test_query_write_blocked(registry):
    b = await registry.get(INSTANCE)
    # sandbox allows writes but let's test a read-only instance config
    from datastore_mcp.config import InstanceConfig
    from datastore_mcp.backends.base import check_write_safety
    cfg = InstanceConfig(type="postgresql", url="unused", allow_write=False)
    with pytest.raises(PermissionError):
        check_write_safety("DELETE FROM pg_stat_activity", cfg, "postgresql")


async def test_schema_inspect_tables(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "tables" in result


async def test_db_stats(registry):
    b = await registry.get(INSTANCE)
    stats = await b.db_stats()
    assert "size_bytes" in stats


async def test_connections(registry):
    b = await registry.get(INSTANCE)
    result = await b.connections()
    assert "connections" in result


async def test_slow_queries_returns_list(registry):
    b = await registry.get(INSTANCE)
    result = await b.slow_queries(limit=5)
    assert isinstance(result, list)


async def test_pg_stat_activity(registry):
    b = await registry.get(INSTANCE)
    result = await b.pg_stat_activity()
    assert isinstance(result, list)


async def test_autovacuum_status(registry):
    b = await registry.get(INSTANCE)
    result = await b.autovacuum_status()
    assert isinstance(result, list)


async def test_bloat_estimate(registry):
    b = await registry.get(INSTANCE)
    result = await b.bloat_estimate()
    assert isinstance(result, list)
