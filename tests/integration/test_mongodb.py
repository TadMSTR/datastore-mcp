"""Integration tests — MongoDB backend against sandbox-db."""
import json
import pytest

INSTANCE = "sandbox-mongo"
pytestmark = pytest.mark.asyncio


async def test_health_check(registry):
    b = await registry.get(INSTANCE)
    h = await b.health_check()
    assert h["status"] == "ok"
    assert "version" in h


async def test_schema_inspect_collections(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "collections" in result
    assert "database" in result


async def test_query_empty_collection(registry):
    b = await registry.get(INSTANCE)
    q = json.dumps({"collection": "test_col", "filter": {}})
    rows = await b.query(q)
    assert isinstance(rows, list)


async def test_query_bad_json_raises(registry):
    b = await registry.get(INSTANCE)
    with pytest.raises(ValueError, match="JSON"):
        await b.query("not json")


async def test_query_missing_collection_raises(registry):
    b = await registry.get(INSTANCE)
    with pytest.raises(ValueError, match="collection"):
        await b.query(json.dumps({"filter": {}}))


async def test_db_stats(registry):
    b = await registry.get(INSTANCE)
    stats = await b.db_stats()
    assert "db" in stats


async def test_server_status(registry):
    b = await registry.get(INSTANCE)
    result = await b.server_status()
    assert "version" in result


async def test_current_op(registry):
    b = await registry.get(INSTANCE)
    result = await b.current_op()
    assert isinstance(result, list)
