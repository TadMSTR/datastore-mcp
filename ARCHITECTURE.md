# Architecture

## Package layout

```
src/datastore_mcp/
├── server.py        FastMCP app; loads config and registry at import time
├── config.py        TOML loader → DatastoreConfig + InstanceConfig (pydantic)
├── registry.py      ConnectionRegistry — lazy Backend init, one per instance
├── backends/
│   ├── base.py      Abstract Backend + _classify_sql() + check_write_safety()
│   ├── postgresql.py asyncpg pool
│   ├── clickhouse.py clickhouse-connect async client
│   ├── mongodb.py    motor AsyncIOMotorClient
│   ├── opensearch.py opensearch-py AsyncOpenSearch
│   ├── influxdb.py   influxdb-client InfluxDBClientAsync (v2.x)
│   ├── valkey.py     redis-py aioredis (Valkey-compatible)
│   ├── mysql.py      aiomysql pool
│   └── sqlite.py     aiosqlite (open/close per op)
└── tools/
    ├── core.py       6 core tools: list_instances, health_check, query,
    │                 schema_inspect, slow_queries, db_stats, connections
    └── extras.py     Backend-specific tools registered for all instances;
                      each validates instance type before delegating
```

## Request flow

```
MCP client → FastMCP → tool function (core/extras)
                           ↓
                      registry.get(instance)     ← lazy init on first call
                           ↓
                      Backend.method()           ← pool acquired per call
                           ↓
                      check_write_safety()       ← sqlglot parse for SQL backends
                           ↓
                      DB driver
```

## Config loading

`load_config()` runs at module import time in `server.py`. If `DATASTORE_MCP_CONFIG`
is unset, defaults to `~/.config/datastore-mcp/config.toml`. A missing config file
causes an immediate startup failure — intentional, not masked.

## Write safety

`check_write_safety()` in `base.py` calls `_classify_sql()` → sqlglot parse.
Returns one of: `select`, `dml`, `ddl`, `other`.
- `select` → always allowed
- `dml` → blocked if `allow_write=False`
- `ddl` → blocked if `allow_ddl=False` (separate flag, never on by default)
- `other` → blocked if `allow_write=False` (unknown → conservative)

Non-SQL backends (MongoDB, OpenSearch, InfluxDB) enforce write safety at the
API level, not via sqlglot.

## Telemetry

OTLP tracing enabled when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Requires
`pip install datastore-mcp[telemetry]`. Span attributes: instance name, backend
type, tool name. Auth fields and query content are never included in spans.
