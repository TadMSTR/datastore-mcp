"""Integration tests — InfluxDB backend against sandbox-db."""
import pytest

INSTANCE = "sandbox-influxdb"
pytestmark = pytest.mark.asyncio


async def test_health_check(registry):
    b = await registry.get(INSTANCE)
    h = await b.health_check()
    assert h["status"] in ("pass", "ok")


async def test_bucket_list(registry):
    b = await registry.get(INSTANCE)
    buckets = await b.bucket_list()
    assert isinstance(buckets, list)
    names = [bk["name"] for bk in buckets]
    assert "sandbox" in names


async def test_schema_inspect_buckets(registry):
    b = await registry.get(INSTANCE)
    result = await b.schema_inspect()
    assert "buckets" in result


async def test_flux_query(registry):
    b = await registry.get(INSTANCE)
    flux = 'buckets() |> limit(n: 5)'
    rows = await b.flux_query(flux)
    assert isinstance(rows, list)


async def test_write_stats(registry):
    b = await registry.get(INSTANCE)
    result = await b.write_stats()
    assert isinstance(result, list)


async def test_slow_queries_empty(registry):
    b = await registry.get(INSTANCE)
    result = await b.slow_queries()
    assert result == []
