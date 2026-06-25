"""Unit tests for backend security guards: Valkey allowlist, InfluxDB Flux write check,
MongoDB JS operator rejection. All DB driver calls are mocked — no live connections needed.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from datastore_mcp.backends.influxdb import InfluxDBBackend, _FLUX_WRITE_PATTERN
from datastore_mcp.backends.mongodb import MongoDBBackend, _JS_OPERATORS, _reject_js_operators
from datastore_mcp.backends.valkey import (
    ValkeyBackend,
    _ALWAYS_BLOCKED,
    _MULTIWORD_READONLY,
    _READONLY_COMMANDS,
)
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


# ---------------------------------------------------------------------------
# Valkey — _ALWAYS_BLOCKED enforcement (H-2)
# ---------------------------------------------------------------------------

class TestValkeyAlwaysBlocked:
    @pytest.mark.parametrize("cmd", sorted(_ALWAYS_BLOCKED))
    async def test_always_blocked_readonly(self, cmd):
        b = _valkey(allow_write=False)
        with pytest.raises(PermissionError, match="not permitted"):
            await b.query(f"{cmd} arg")

    @pytest.mark.parametrize("cmd", ["EVAL", "DEBUG", "SHUTDOWN", "CONFIG", "ACL"])
    async def test_always_blocked_even_with_write(self, cmd):
        """_ALWAYS_BLOCKED must fire even when allow_write=True."""
        b = _valkey(allow_write=True)
        with pytest.raises(PermissionError, match="not permitted"):
            await b.query(f"{cmd} arg")

    async def test_empty_command_raises(self):
        b = _valkey()
        with pytest.raises(ValueError, match="Empty command"):
            await b.query("")


# ---------------------------------------------------------------------------
# Valkey — read-only allowlist enforcement (H-2)
# ---------------------------------------------------------------------------

class TestValkeyReadonlyAllowlist:
    @pytest.mark.parametrize("cmd", [
        "GET", "MGET", "KEYS", "SCAN", "PING", "ECHO",
        "HGET", "HGETALL", "LRANGE", "SMEMBERS", "ZRANGE",
        "EXISTS", "TYPE", "TTL", "INFO", "DBSIZE",
    ])
    async def test_readonly_commands_allowed(self, cmd):
        b = _valkey(allow_write=False)
        result = await b.query(f"{cmd} somekey")
        assert isinstance(result, list)

    @pytest.mark.parametrize("cmd", ["SET", "DEL", "EXPIRE", "HSET", "LPUSH", "SADD", "ZADD"])
    async def test_write_commands_blocked_readonly(self, cmd):
        b = _valkey(allow_write=False)
        with pytest.raises(PermissionError, match="read-only allowlist"):
            await b.query(f"{cmd} somekey somevalue")

    @pytest.mark.parametrize("cmd", ["SET", "DEL", "HSET", "LPUSH", "EXPIRE"])
    async def test_write_commands_allowed_with_flag(self, cmd):
        b = _valkey(allow_write=True)
        result = await b.query(f"{cmd} somekey somevalue")
        assert isinstance(result, list)

    async def test_unknown_command_blocked_readonly(self):
        """A command not in the allowlist must be rejected."""
        b = _valkey(allow_write=False)
        with pytest.raises(PermissionError):
            await b.query("FLUSHDB")

    async def test_unknown_command_blocked_even_not_in_multiword(self):
        """FLUSHDB is write-only and not in _MULTIWORD_READONLY."""
        assert "FLUSHDB" not in _READONLY_COMMANDS
        assert "FLUSHDB" not in _MULTIWORD_READONLY
        b = _valkey(allow_write=False)
        with pytest.raises(PermissionError):
            await b.query("FLUSHDB")


# ---------------------------------------------------------------------------
# Valkey — multi-word command enforcement (H-2)
# ---------------------------------------------------------------------------

class TestValkeyMultiwordCommands:
    @pytest.mark.parametrize("query,allowed", [
        ("SLOWLOG GET 10", True),
        ("SLOWLOG LEN", True),
        ("SLOWLOG HELP", True),
        ("SLOWLOG RESET", False),
        ("CLIENT LIST", True),
        ("CLIENT ID", True),
        ("CLIENT KILL addr:1234", False),
        ("MEMORY USAGE mykey", True),
        ("MEMORY DOCTOR", True),
        ("MEMORY PURGE", False),
        ("LATENCY HISTORY event", True),
        ("LATENCY LATEST", True),
        ("LATENCY RESET", False),
        ("CLUSTER INFO", True),
        ("CLUSTER RESET", False),
        ("XINFO STREAM mystream", True),
        ("XINFO HELP", True),
        ("COMMAND COUNT", True),
        ("COMMAND DOCS GET", True),
        ("COMMAND RESET", False),
    ])
    async def test_multiword_enforcement(self, query, allowed):
        b = _valkey(allow_write=False)
        if allowed:
            result = await b.query(query)
            assert isinstance(result, list)
        else:
            with pytest.raises(PermissionError):
                await b.query(query)

    async def test_multiword_allowed_with_write_flag(self):
        """With allow_write=True, multiword subcommand restrictions are lifted."""
        b = _valkey(allow_write=True)
        result = await b.query("SLOWLOG RESET")
        assert isinstance(result, list)

    async def test_multiword_missing_subcommand_blocked(self):
        """SLOWLOG with no subcommand must be rejected read-only."""
        b = _valkey(allow_write=False)
        with pytest.raises(PermissionError):
            await b.query("SLOWLOG")


# ---------------------------------------------------------------------------
# InfluxDB — _FLUX_WRITE_PATTERN regex
# ---------------------------------------------------------------------------

class TestFluxWritePattern:
    @pytest.mark.parametrize("flux", [
        'from(bucket:"foo") |> range(start:-1h) |> to(bucket:"bar")',
        'from(bucket:"foo") |> range(start:-1h) |> to(bucket:"bar", org:"myorg")',
        'from(bucket:"foo") |> experimental.to(bucket:"bar")',
        'from(bucket:"foo") |>to(bucket:"bar")',          # no space after |>
        'from(bucket:"foo") |>  to(bucket:"bar")',        # extra space
        'from(bucket:"foo") |> TO(bucket:"bar")',         # uppercase
    ])
    def test_write_patterns_detected(self, flux):
        assert _FLUX_WRITE_PATTERN.search(flux) is not None

    @pytest.mark.parametrize("flux", [
        'from(bucket:"foo") |> range(start:-1h)',
        'from(bucket:"foo") |> filter(fn:(r) => r._measurement == "cpu")',
        'from(bucket:"foo") |> toString()',               # "to" but not |> to(
        'from(bucket:"foo") |> toFloat()',                # same
        'from(bucket:"foo") |> map(fn:(r) => ({ r with total: r._value }))',
    ])
    def test_safe_patterns_not_detected(self, flux):
        assert _FLUX_WRITE_PATTERN.search(flux) is None


# ---------------------------------------------------------------------------
# InfluxDB — _check_flux_write method (M-3a)
# ---------------------------------------------------------------------------

class TestInfluxDBCheckFluxWrite:
    def test_write_pattern_blocked_readonly(self):
        b = _influx(allow_write=False)
        with pytest.raises(PermissionError, match="write operation"):
            b._check_flux_write('from(bucket:"foo") |> to(bucket:"bar")')

    def test_experimental_to_blocked_readonly(self):
        b = _influx(allow_write=False)
        with pytest.raises(PermissionError, match="write operation"):
            b._check_flux_write('from(bucket:"foo") |> experimental.to(bucket:"bar")')

    def test_write_pattern_allowed_with_flag(self):
        b = _influx(allow_write=True)
        b._check_flux_write('from(bucket:"foo") |> to(bucket:"bar")')  # no exception

    def test_safe_query_not_blocked(self):
        b = _influx(allow_write=False)
        b._check_flux_write('from(bucket:"foo") |> range(start:-1h)')  # no exception


# ---------------------------------------------------------------------------
# InfluxDB — query() and flux_query() gate (M-3a)
# ---------------------------------------------------------------------------

class TestInfluxDBQueryGate:
    async def test_query_blocks_write_flux(self):
        b = _influx(allow_write=False)
        with pytest.raises(PermissionError, match="write operation"):
            await b.query('from(bucket:"foo") |> to(bucket:"bar")')

    async def test_flux_query_blocks_write_flux(self):
        b = _influx(allow_write=False)
        with pytest.raises(PermissionError, match="write operation"):
            await b.flux_query('from(bucket:"foo") |> to(bucket:"bar")')

    async def test_query_blocks_experimental_to(self):
        b = _influx(allow_write=False)
        with pytest.raises(PermissionError, match="write operation"):
            await b.query('from(bucket:"foo") |> experimental.to(bucket:"bar")')

    async def test_query_proceeds_with_safe_flux(self):
        b = _influx(allow_write=False)
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(return_value=[])
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.query('from(bucket:"foo") |> range(start:-1h)')
        assert result == []
        mock_qapi.query.assert_called_once()

    async def test_flux_query_proceeds_with_safe_flux(self):
        b = _influx(allow_write=False)
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(return_value=[])
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.flux_query('from(bucket:"foo") |> range(start:-1h)')
        assert result == []
        mock_qapi.query.assert_called_once()

    async def test_query_with_write_flag_proceeds(self):
        b = _influx(allow_write=True)
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(return_value=[])
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.query('from(bucket:"foo") |> to(bucket:"bar")')
        assert result == []


# ---------------------------------------------------------------------------
# MongoDB — _reject_js_operators (M-2)
# ---------------------------------------------------------------------------

class TestRejectJsOperators:
    @pytest.mark.parametrize("op", sorted(_JS_OPERATORS))
    def test_top_level_js_operators_blocked(self, op):
        with pytest.raises(ValueError, match="not permitted"):
            _reject_js_operators({op: "some code"})

    def test_nested_in_dict_blocked(self):
        with pytest.raises(ValueError, match="not permitted"):
            _reject_js_operators({"a": {"$where": "this.x > 1"}})

    def test_nested_in_list_blocked(self):
        with pytest.raises(ValueError, match="not permitted"):
            _reject_js_operators({"$or": [{"$where": "1 == 1"}, {}]})

    def test_deeply_nested_blocked(self):
        with pytest.raises(ValueError, match="not permitted"):
            _reject_js_operators({
                "a": {"b": {"c": {"$function": {"body": "return true", "args": [], "lang": "js"}}}}
            })

    def test_list_containing_nested_js_blocked(self):
        with pytest.raises(ValueError, match="not permitted"):
            _reject_js_operators([{"status": "active"}, {"$accumulator": {}}])

    def test_clean_filter_allowed(self):
        _reject_js_operators({"status": "active", "count": {"$gt": 5}})

    def test_empty_doc_allowed(self):
        _reject_js_operators({})

    def test_none_allowed(self):
        _reject_js_operators(None)

    def test_scalar_string_allowed(self):
        _reject_js_operators("just a string")

    def test_list_of_clean_docs_allowed(self):
        _reject_js_operators([{"a": 1}, {"b": {"$gte": 0}}])

    def test_dollar_field_not_js_allowed(self):
        """$gt, $gte, $lt, $in etc. must not be blocked — only JS operators."""
        _reject_js_operators({
            "price": {"$gte": 10, "$lte": 100},
            "tags": {"$in": ["a", "b"]},
            "name": {"$regex": "^foo", "$options": "i"},
        })


# ---------------------------------------------------------------------------
# MongoDB — query() integration (M-2)
# ---------------------------------------------------------------------------

class TestMongoDBQuery:
    def _with_mock_collection(self, docs: list) -> tuple[MongoDBBackend, MagicMock]:
        """Return a backend wired to a mock collection that returns `docs`."""
        b = _mongo()
        cursor = MagicMock()
        cursor.sort = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(return_value=docs)
        coll = MagicMock()
        coll.find = MagicMock(return_value=cursor)
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=coll)
        b._client = MagicMock()
        b._client.__getitem__ = MagicMock(return_value=db)
        return b, coll

    async def test_where_in_filter_blocked(self):
        b = _mongo()
        q = json.dumps({"collection": "users", "filter": {"$where": "1 == 1"}})
        with pytest.raises(ValueError, match="not permitted"):
            await b.query(q)

    async def test_function_in_filter_blocked(self):
        b = _mongo()
        q = json.dumps({
            "collection": "users",
            "filter": {"score": {"$function": {"body": "return true", "args": [], "lang": "js"}}},
        })
        with pytest.raises(ValueError, match="not permitted"):
            await b.query(q)

    async def test_nested_js_operator_blocked(self):
        b = _mongo()
        q = json.dumps({
            "collection": "logs",
            "filter": {"$or": [{"$where": "this.level == 'error'"}, {"level": "warning"}]},
        })
        with pytest.raises(ValueError, match="not permitted"):
            await b.query(q)

    async def test_invalid_json_rejected(self):
        b = _mongo()
        with pytest.raises(ValueError, match="JSON"):
            await b.query("not valid json")

    async def test_missing_collection_key_rejected(self):
        b = _mongo()
        with pytest.raises(ValueError, match="collection"):
            await b.query(json.dumps({"filter": {"status": "active"}}))

    async def test_safe_query_executes(self):
        b, coll = self._with_mock_collection([{"_id": "abc", "name": "test"}])
        q = json.dumps({"collection": "users", "filter": {"status": "active"}})
        result = await b.query(q)
        assert len(result) == 1
        assert result[0]["name"] == "test"
        coll.find.assert_called_once_with({"status": "active"}, None)

    async def test_id_converted_to_string(self):
        """_id values must be serialised to str in the returned docs."""
        b, _ = self._with_mock_collection([{"_id": "507f1f77bcf86cd799439011", "x": 1}])
        q = json.dumps({"collection": "things", "filter": {}})
        result = await b.query(q)
        assert isinstance(result[0]["_id"], str)

    async def test_query_with_sort(self):
        b, coll = self._with_mock_collection([{"_id": "abc", "name": "test"}])
        q = json.dumps({
            "collection": "users",
            "filter": {"status": "active"},
            "sort": {"name": 1},
        })
        result = await b.query(q)
        assert len(result) == 1
        coll.find.return_value.sort.assert_called_once_with([("name", 1)])


# ---------------------------------------------------------------------------
# Backend method coverage — helper methods tested via mocks
# ---------------------------------------------------------------------------

class TestValkeyHelperMethods:
    async def test_close(self):
        b = _valkey()
        b._client.aclose = AsyncMock()
        await b.close()
        b._client.aclose.assert_called_once()

    async def test_health_check_ok(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={"redis_version": "7.2.0", "uptime_in_seconds": 42})
        b._client.ping = AsyncMock(return_value=True)
        result = await b.health_check()
        assert result["status"] == "ok"
        assert result["redis_version"] == "7.2.0"

    async def test_health_check_error(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={})
        b._client.ping = AsyncMock(return_value=False)
        result = await b.health_check()
        assert result["status"] == "error"

    async def test_query_returns_list(self):
        """When execute_command returns a list, each item is wrapped in a value dict."""
        b = _valkey()
        b._client.execute_command = AsyncMock(return_value=["key1", "key2"])
        result = await b.query("KEYS *")
        assert result == [{"value": "key1"}, {"value": "key2"}]

    async def test_slow_queries(self):
        b = _valkey()
        b._client.slowlog_get = AsyncMock(return_value=[
            {"id": 1, "duration": 500, "command": "GET foo"},
        ])
        result = await b.slow_queries()
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["duration_us"] == 500

    async def test_db_stats(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={
            "used_memory_human": "1.5M",
            "total_commands_processed": 1000,
            "connected_clients": 3,
            "keyspace_hits": 900,
            "keyspace_misses": 100,
        })
        result = await b.db_stats()
        assert result["used_memory_human"] == "1.5M"
        assert result["connected_clients"] == 3

    async def test_connections(self):
        b = _valkey()
        b._client.client_list = AsyncMock(return_value=[{"id": 1, "addr": "127.0.0.1:12345"}])
        result = await b.connections()
        assert "clients" in result
        assert len(result["clients"]) == 1

    async def test_schema_inspect_no_table(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={"db0": "keys=10,expires=2", "maxmemory": 0})
        result = await b.schema_inspect()
        assert "keyspace" in result
        assert "db0" in result["keyspace"]

    async def test_keyspace_stats(self):
        b = _valkey()
        b._client.info = AsyncMock(return_value={"db0": "keys=10,expires=2", "other": "x"})
        result = await b.keyspace_stats()
        assert "db0" in result
        assert "other" not in result

    async def test_client_list(self):
        b = _valkey()
        b._client.client_list = AsyncMock(return_value=[{"id": 1}])
        result = await b.client_list()
        assert result == [{"id": 1}]


class TestInfluxDBHelperMethods:
    async def test_slow_queries_returns_empty(self):
        result = await _influx().slow_queries()
        assert result == []

    async def test_connections_returns_empty(self):
        result = await _influx().connections()
        assert result == {}

    async def test_query_returns_records(self):
        """Lines 82-83: inner loop over table records."""
        b = _influx(allow_write=False)
        mock_record = MagicMock()
        mock_record.values = {"_field": "usage", "_value": 0.5}
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        mock_qapi = MagicMock()
        mock_qapi.query = AsyncMock(return_value=[mock_table])
        b._client.query_api = MagicMock(return_value=mock_qapi)
        result = await b.query('from(bucket:"metrics") |> range(start:-1h)')
        assert len(result) == 1
        assert result[0]["_field"] == "usage"

    def _mock_buckets_response(self, b: InfluxDBBackend, buckets: list) -> None:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"buckets": buckets})
        b._http.get = AsyncMock(return_value=response)

    async def test_list_buckets(self):
        b = _influx()
        self._mock_buckets_response(b, [
            {"name": "metrics", "id": "abc", "retentionRules": []},
            {"name": "logs", "id": "def", "retentionRules": []},
        ])
        result = await b._list_buckets()
        assert len(result) == 2
        assert result[0]["name"] == "metrics"

    async def test_db_stats(self):
        b = _influx()
        self._mock_buckets_response(b, [
            {"name": "metrics", "id": "abc", "retentionRules": []},
        ])
        result = await b.db_stats()
        assert result["bucket_count"] == 1
        assert result["org"] == "testorg"

    async def test_bucket_list(self):
        b = _influx()
        self._mock_buckets_response(b, [
            {"name": "metrics", "id": "abc", "retentionRules": []},
        ])
        result = await b.bucket_list()
        assert len(result) == 1


class TestMongoDBHelperMethods:
    async def test_close(self):
        b = _mongo()
        await b.close()
        b._client.close.assert_called_once()

    async def test_health_check(self):
        b = _mongo()
        b._client.server_info = AsyncMock(return_value={"version": "7.0.0", "maxWireVersion": 17})
        result = await b.health_check()
        assert result["status"] == "ok"
        assert result["version"] == "7.0.0"

    def _mock_db(self, b: MongoDBBackend) -> MagicMock:
        mock_db = MagicMock()
        b._client.__getitem__ = MagicMock(return_value=mock_db)
        return mock_db

    async def test_db_stats(self):
        b = _mongo()
        db = self._mock_db(b)
        db.command = AsyncMock(return_value={
            "db": "testdb", "collections": 5,
            "dataSize": 1000, "storageSize": 2000,
            "indexSize": 500, "objects": 100,
        })
        result = await b.db_stats()
        assert result["db"] == "testdb"
        assert result["collections"] == 5

    async def test_connections(self):
        b = _mongo()
        b._client.admin.command = AsyncMock(return_value={
            "connections": {"current": 5, "available": 95, "totalCreated": 100}
        })
        result = await b.connections()
        assert result["current"] == 5
        assert result["available"] == 95

    async def test_schema_inspect_no_table(self):
        b = _mongo()
        db = self._mock_db(b)
        db.list_collection_names = AsyncMock(return_value=["users", "logs"])
        result = await b.schema_inspect()
        assert result["database"] == "testdb"
        assert "users" in result["collections"]
        assert "logs" in result["collections"]
