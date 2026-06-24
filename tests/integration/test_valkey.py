"""Integration tests — Valkey backend against sandbox-db."""
import pytest

INSTANCE = "sandbox-valkey"
pytestmark = pytest.mark.asyncio


async def test_health_check(registry):
    b = await registry.get(INSTANCE)
    h = await b.health_check()
    assert h["status"] == "ok"
    assert "redis_version" in h


async def test_query_ping(registry):
    b = await registry.get(INSTANCE)
    rows = await b.query("PING")
    assert rows[0]["value"] in (True, "PONG")


async def test_query_write_blocked(registry):
    from datastore_mcp.backends.valkey import _ALWAYS_BLOCKED, _READONLY_COMMANDS
    # Allowlist must not include write commands
    assert "SET" not in _READONLY_COMMANDS
    assert "EVAL" in _ALWAYS_BLOCKED
    # Read commands must be on the allowlist
    assert "GET" in _READONLY_COMMANDS


async def test_schema_inspect_keyspace(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "keyspace" in result


async def test_server_info(registry):
    b = await registry.get(INSTANCE)
    info = await b.server_info()
    assert "redis_version" in info


async def test_db_stats(registry):
    b = await registry.get(INSTANCE)
    stats = await b.db_stats()
    assert "used_memory_human" in stats


async def test_slow_log(registry):
    b = await registry.get(INSTANCE)
    result = await b.slow_log(limit=5)
    assert isinstance(result, list)


async def test_memory_usage_doctor(registry):
    b = await registry.get(INSTANCE)
    result = await b.memory_usage()
    assert "doctor" in result


async def test_keyspace_stats(registry):
    b = await registry.get(INSTANCE)
    result = await b.keyspace_stats()
    assert isinstance(result, dict)
