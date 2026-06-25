"""Unit tests for backend methods not covered by test_security_guards.py.

Covers: schema_inspect branches, close/health_check, extra methods
(write_stats, current_op, server_status, coll_stats, index_stats,
server_info, slow_log, memory_usage) and the base._classify_sql
exception path. All DB driver calls are mocked.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from datastore_mcp.backends.base import _classify_sql
from datastore_mcp.backends.influxdb import InfluxDBBackend
from datastore_mcp.backends.mongodb import MongoDBBackend
from datastore_mcp.backends.valkey import ValkeyBackend
from datastore_mcp.config import InstanceConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vcfg(allow_write: bool = False) -> InstanceConfig:
    return InstanceConfig(type="valkey", url="valkey://localhost:6379", allow_write=allow_write)


def _valkey(allow_write: bool = False) -> ValkeyBackend:
    client = MagicMock()
    client.execute_command = AsyncMock(return_value="OK")
    return ValkeyBackend("test", _vcfg(allow_write), client)


def _icfg(allow_write: bool = False) -> InstanceConfig:
    return InstanceConfig(
        type="influxdb",
        url="http://localhost:8086",
        allow_write=allow_write,
        token="testtoken",
        org="testorg",
        bucket="testbucket",
    )


def _influx(allow_write: bool = False) -> InfluxDBBackend:
    return InfluxDBBackend("test", _icfg(allow_write), MagicMock(), MagicMock())


def _mcfg() -> InstanceConfig:
    return InstanceConfig(type="mongodb", url="mongodb://localhost:27017/testdb")


def _mongo() -> MongoDBBackend:
    return MongoDBBackend("test", _mcfg(), MagicMock(), "testdb")


def _mock_influx_buckets(b: InfluxDBBackend, buckets: list) -> None:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"buckets": buckets})
    b._http.get = AsyncMock(return_value=response)


def _mock_mongo_db(b: MongoDBBackend) -> MagicMock:
    mock_db = MagicMock()
    b._client.__getitem__ = MagicMock(return_value=mock_db)
    return mock_db


# ---------------------------------------------------------------------------
# base._classify_sql — exception path (lines 32-33)
# ---------------------------------------------------------------------------

class TestClassifySqlException:
    def test_returns_other_on_parse_error(self):
        with patch("datastore_mcp.backends.base.sqlglot.parse_one", side_effect=Exception("bad")):
            assert _classify_sql("SELECT 1", "postgres") == "other"


# ---------------------------------------------------------------------------
# InfluxDB — close, health_check, _auth_headers (lines 38, 51-52, 55-57)
# ---------------------------------------------------------------------------

class TestInfluxDBLifecycle:
    async def test_close(self):
        b = _influx()
        b._client.close = AsyncMock()
        b._http.aclose = AsyncMock()
        await b.close()
        b._client.close.assert_called_once()
        b._http.aclose.assert_called_once()

    async def test_health_check_pass(self):
        b = _influx()
        b._client.ping = AsyncMock(return_value=True)
        b._client.version = AsyncMock(return_value="2.7.6")
        result = await b.health_check()
        assert result["status"] == "pass"
        assert result["version"] == "2.7.6"

    async def test_health_check_error(self):
        b = _influx()
        b._client.ping = AsyncMock(return_value=False)
        b._client.version = AsyncMock(return_value="2.7.6")
        result = await b.health_check()
        assert result["status"] == "error"

    def test_auth_headers(self):
        b = _influx()
        assert b._auth_headers == {"Authorization": "Token testtoken"}


# ---------------------------------------------------------------------------
# InfluxDB — schema_inspect (lines 87-111)
# ---------------------------------------------------------------------------

class TestInfluxDBSchemaInspect:
    def _mock_qapi(self, b: InfluxDBBackend, records=None) -> MagicMock:
        mock_record = MagicMock()
        mock_record.get_value = MagicMock(return_value="cpu")
        mock_table = MagicMock()
        mock_table.records = [mock_record] if records is None else records
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(return_value=[mock_table])
        b._client.query_api = MagicMock(return_value=mock_qapi)
        return mock_qapi

    async def test_schema_inspect_no_table(self):
        b = _influx()
        _mock_influx_buckets(b, [{"name": "metrics", "id": "abc", "retentionRules": []}])
        result = await b.schema_inspect()
        assert "buckets" in result
        assert result["buckets"][0]["name"] == "metrics"

    async def test_schema_inspect_with_table_success(self):
        b = _influx()
        _mock_influx_buckets(b, [{"name": "metrics", "id": "abc", "retentionRules": []}])
        self._mock_qapi(b)
        result = await b.schema_inspect(table="metrics")
        assert result["bucket"] == "metrics"
        assert "cpu" in result["measurements"]

    async def test_schema_inspect_unknown_bucket_raises(self):
        b = _influx()
        _mock_influx_buckets(b, [{"name": "metrics", "id": "abc", "retentionRules": []}])
        with pytest.raises(ValueError, match="Unknown bucket"):
            await b.schema_inspect(table="nonexistent")

    async def test_schema_inspect_query_error_returns_error_key(self):
        b = _influx()
        _mock_influx_buckets(b, [{"name": "metrics", "id": "abc", "retentionRules": []}])
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(side_effect=RuntimeError("flux error"))
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.schema_inspect(table="metrics")
        assert result["bucket"] == "metrics"
        assert "error" in result
        assert "flux error" in result["error"]


# ---------------------------------------------------------------------------
# InfluxDB — write_stats (lines 149-163)
# ---------------------------------------------------------------------------

class TestInfluxDBWriteStats:
    async def test_write_stats_success(self):
        b = _influx()
        mock_record = MagicMock()
        mock_record.values = {"_field": "writeOk", "_value": 5}
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(return_value=[mock_table])
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.write_stats()
        assert len(result) == 1
        assert result[0]["_field"] == "writeOk"

    async def test_write_stats_exception_returns_empty(self):
        b = _influx()
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(side_effect=RuntimeError("unavailable"))
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.write_stats()
        assert result == []


# ---------------------------------------------------------------------------
# MongoDB — schema_inspect with table (lines 98-107)
# ---------------------------------------------------------------------------

class TestMongoDBSchemaInspect:
    async def test_schema_inspect_with_table_and_id(self):
        b = _mongo()
        db = _mock_mongo_db(b)
        coll = MagicMock()
        coll.estimated_document_count = AsyncMock(return_value=42)
        coll.find_one = AsyncMock(return_value={"_id": "abc123", "name": "test"})
        db.__getitem__ = MagicMock(return_value=coll)
        result = await b.schema_inspect(table="users")
        assert result["collection"] == "users"
        assert result["estimated_count"] == 42
        assert result["sample_document"]["_id"] == "abc123"
        assert isinstance(result["sample_document"]["_id"], str)

    async def test_schema_inspect_with_table_no_sample(self):
        b = _mongo()
        db = _mock_mongo_db(b)
        coll = MagicMock()
        coll.estimated_document_count = AsyncMock(return_value=0)
        coll.find_one = AsyncMock(return_value=None)
        db.__getitem__ = MagicMock(return_value=coll)
        result = await b.schema_inspect(table="empty_coll")
        assert result["estimated_count"] == 0
        assert result["sample_document"] is None


# ---------------------------------------------------------------------------
# MongoDB — slow_queries (lines 110-125)
# ---------------------------------------------------------------------------

class TestMongoDBSlowQueries:
    async def test_slow_queries_returns_ops(self):
        b = _mongo()
        b._client.admin.command = AsyncMock(return_value={
            "inprog": [
                {"op": "query", "ns": "db.users", "secs_running": 5, "desc": "slow op"},
            ]
        })
        result = await b.slow_queries(limit=10)
        assert len(result) == 1
        assert result[0]["op"] == "query"
        assert result[0]["secs_running"] == 5

    async def test_slow_queries_exception_returns_empty(self):
        b = _mongo()
        b._client.admin.command = AsyncMock(side_effect=RuntimeError("not authorized"))
        result = await b.slow_queries()
        assert result == []

    async def test_slow_queries_respects_limit(self):
        b = _mongo()
        b._client.admin.command = AsyncMock(return_value={
            "inprog": [{"op": "q", "ns": "x", "secs_running": i, "desc": ""} for i in range(20)]
        })
        result = await b.slow_queries(limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# MongoDB — extra methods (lines 150-191)
# ---------------------------------------------------------------------------

class TestMongoDBExtraMethods:
    async def test_current_op(self):
        b = _mongo()
        b._client.admin.command = AsyncMock(return_value={
            "inprog": [{"op": "query", "ns": "db.x", "secs_running": 2, "client": "127.0.0.1", "desc": "op"}]
        })
        result = await b.current_op()
        assert len(result) == 1
        assert result[0]["op"] == "query"
        assert result[0]["client"] == "127.0.0.1"

    async def test_server_status(self):
        b = _mongo()
        b._client.admin.command = AsyncMock(return_value={
            "version": "7.0.0",
            "uptime": 3600,
            "connections": {"current": 5},
            "opcounters": {"query": 1000},
            "mem": {"resident": 256},
        })
        result = await b.server_status()
        assert result["version"] == "7.0.0"
        assert result["uptime"] == 3600

    async def test_coll_stats(self):
        b = _mongo()
        db = _mock_mongo_db(b)
        db.command = AsyncMock(return_value={
            "ns": "testdb.users",
            "count": 100,
            "size": 8192,
            "storageSize": 16384,
            "indexSizes": {"_id_": 4096},
            "avgObjSize": 82,
        })
        result = await b.coll_stats("users")
        assert result["ns"] == "testdb.users"
        assert result["count"] == 100
        assert result["index_sizes"] == {"_id_": 4096}

    async def test_index_stats(self):
        b = _mongo()
        db = _mock_mongo_db(b)
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[
            {"name": "_id_", "accesses": {"ops": 42}},
            {"name": "name_1", "accesses": {"ops": 7}},
        ])
        coll = MagicMock()
        coll.aggregate = MagicMock(return_value=cursor)
        db.__getitem__ = MagicMock(return_value=coll)
        result = await b.index_stats("users")
        assert len(result) == 2
        assert result[0]["name"] == "_id_"
        assert result[0]["accesses"] == 42
        coll.aggregate.assert_called_once_with([{"$indexStats": {}}])


# ---------------------------------------------------------------------------
# Valkey — schema_inspect with table (lines 122-131)
# ---------------------------------------------------------------------------

class TestValkeySchemaInspectWithTable:
    async def test_schema_inspect_with_table_single_scan(self):
        """Scan returns cursor=0 on first call → loop exits immediately."""
        b = _valkey()
        b._client.info = AsyncMock(return_value={"db0": "keys=5"})
        b._client.scan = AsyncMock(return_value=(0, ["user:1", "user:2"]))
        result = await b.schema_inspect(table="user:*")
        assert result["pattern"] == "user:*"
        assert result["matching_keys"] == ["user:1", "user:2"]

    async def test_schema_inspect_with_table_multi_scan(self):
        """Scan returns non-zero cursor on first call, then 0 on second."""
        b = _valkey()
        b._client.info = AsyncMock(return_value={})
        b._client.scan = AsyncMock(side_effect=[
            (99, ["key:1", "key:2"]),
            (0,  ["key:3"]),
        ])
        result = await b.schema_inspect(table="key:*")
        assert result["matching_keys"] == ["key:1", "key:2", "key:3"]

    async def test_schema_inspect_with_table_empty_result(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={})
        b._client.scan = AsyncMock(return_value=(0, []))
        result = await b.schema_inspect(table="missing:*")
        assert result["matching_keys"] == []


# ---------------------------------------------------------------------------
# Valkey — extra methods (lines 158, 161-162, 168-172)
# ---------------------------------------------------------------------------

class TestValkeyExtraMethods:
    async def test_server_info(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={"redis_version": "7.2.0", "uptime_in_seconds": 100})
        result = await b.server_info()
        assert result["redis_version"] == "7.2.0"

    async def test_slow_log(self):
        b = _valkey()
        b._client.slowlog_get = AsyncMock(return_value=[
            {"id": 5, "duration": 1200, "command": "KEYS *"},
        ])
        result = await b.slow_log(limit=5)
        assert len(result) == 1
        assert result[0]["id"] == 5
        assert result[0]["duration_us"] == 1200

    async def test_slow_log_empty(self):
        b = _valkey()
        b._client.slowlog_get = AsyncMock(return_value=[])
        result = await b.slow_log()
        assert result == []

    async def test_memory_usage_with_key(self):
        b = _valkey()
        b._client.memory_usage = AsyncMock(return_value=1024)
        result = await b.memory_usage(key="mykey")
        assert result == {"key": "mykey", "bytes": 1024}
        b._client.memory_usage.assert_called_once_with("mykey")

    async def test_memory_usage_without_key(self):
        b = _valkey()
        b._client.execute_command = AsyncMock(return_value="Your memory is fine")
        result = await b.memory_usage()
        assert result == {"doctor": "Your memory is fine"}
        b._client.execute_command.assert_called_once_with("MEMORY DOCTOR")
