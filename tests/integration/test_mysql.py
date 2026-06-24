"""Integration tests — MySQL backend against sandbox-db."""
import pytest

INSTANCE = "sandbox-mysql"
pytestmark = pytest.mark.asyncio


async def test_health_check(registry):
    b = await registry.get(INSTANCE)
    h = await b.health_check()
    assert h["status"] == "ok"
    assert "version" in h


async def test_query_select(registry):
    b = await registry.get(INSTANCE)
    rows = await b.query("SELECT 1 AS n")
    assert rows[0]["n"] == 1


async def test_schema_inspect_tables(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "tables" in result


async def test_db_stats(registry):
    b = await registry.get(INSTANCE)
    stats = await b.db_stats()
    assert "databases" in stats


async def test_processlist(registry):
    b = await registry.get(INSTANCE)
    result = await b.processlist()
    assert isinstance(result, list)


async def test_innodb_status(registry):
    b = await registry.get(INSTANCE)
    result = await b.innodb_status()
    assert isinstance(result, dict)


async def test_table_stats(registry):
    b = await registry.get(INSTANCE)
    result = await b.table_stats()
    assert isinstance(result, list)


async def test_slow_queries_returns_list(registry):
    b = await registry.get(INSTANCE)
    result = await b.slow_queries(limit=5)
    assert isinstance(result, list)
