"""Integration tests — ClickHouse backend against sandbox-db."""
import pytest

INSTANCE = "sandbox-clickhouse"
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


async def test_schema_inspect(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "tables" in result


async def test_db_stats(registry):
    b = await registry.get(INSTANCE)
    stats = await b.db_stats()
    assert "databases" in stats


async def test_parts_info(registry):
    b = await registry.get(INSTANCE)
    result = await b.parts_info()
    assert isinstance(result, list)


async def test_merges(registry):
    b = await registry.get(INSTANCE)
    result = await b.merges()
    assert isinstance(result, list)
