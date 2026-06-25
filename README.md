# datastore-mcp

Multi-backend database MCP server for homelab and self-hosted environments. Exposes query, inspection, and diagnostic tools across 8 database backends via a single FastMCP server.

[![CI](https://github.com/TadMSTR/datastore-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/TadMSTR/datastore-mcp/actions/workflows/ci.yml)

## Backends

| Backend | Driver | Notes |
|---|---|---|
| PostgreSQL | asyncpg | Connection pool |
| ClickHouse | clickhouse-connect | Async HTTP client |
| MongoDB | motor | AsyncIOMotorClient |
| OpenSearch | opensearch-py | AsyncOpenSearch |
| InfluxDB | influxdb-client | v2.x API (Flux); not InfluxDB 3 SQL |
| Valkey / Redis | redis-py | Fully Redis-protocol-compatible |
| MySQL | aiomysql | Connection pool |
| SQLite | aiosqlite | Opens/closes per query; no pool |

## Installation

```bash
# Base install (no DB drivers)
pip install datastore-mcp

# With specific backends
pip install "datastore-mcp[postgresql,mongodb]"

# All backends (bundles the OTLP exporter — no separate telemetry extra needed)
pip install "datastore-mcp[all]"

# A partial backend selection plus OTLP tracing
pip install "datastore-mcp[postgresql,telemetry]"
```

Requires Python 3.11+.

## Quick start

1. Create a config file:

```toml
# ~/.config/datastore-mcp/config.toml

[instances.my-pg]
type = "postgresql"
url = "postgresql://user:pass@localhost:5432/mydb"

[instances.my-mongo]
type = "mongodb"
url = "mongodb://user:pass@localhost:27017/mydb"
allow_write = true
```

2. Run:

```bash
datastore-mcp
# or
DATASTORE_MCP_CONFIG=/path/to/config.toml datastore-mcp
```

The server starts on `127.0.0.1:8501` by default.

## Configuration

Set `DATASTORE_MCP_CONFIG` to point at your TOML file, or place it at `~/.config/datastore-mcp/config.toml`. A missing config file causes an immediate startup failure — not silently ignored.

### Instance fields

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | required | Backend type (see table above) |
| `url` | string | required | Connection URL |
| `allow_write` | bool | `false` | Permit INSERT/UPDATE/DELETE and write commands |
| `allow_ddl` | bool | `false` | Permit CREATE/DROP/ALTER and unclassified statements |
| `user` | string | — | ClickHouse username |
| `password` | string | — | ClickHouse password |
| `token` | string | — | InfluxDB API token |
| `org` | string | — | InfluxDB organisation |
| `bucket` | string | — | InfluxDB default bucket |

### Full config example

```toml
[instances.prod-pg]
type = "postgresql"
url = "postgresql://readonly:secret@db.internal:5432/app"
allow_write = false

[instances.prod-ch]
type = "clickhouse"
url = "http://ch.internal:8123"
user = "default"
password = ""
allow_write = false

[instances.prod-mongo]
type = "mongodb"
url = "mongodb://readonly:secret@mongo.internal:27017/app"
allow_write = false

[instances.prod-influx]
type = "influxdb"
url = "http://influx.internal:8086"
token = "my-read-token"
org = "myorg"
allow_write = false

[instances.cache]
type = "valkey"
url = "redis://:secret@localhost:6379"
allow_write = false

[instances.dev-sqlite]
type = "sqlite"
url = "sqlite:////var/db/dev.sqlite"
allow_write = true
allow_ddl = true
```

## Tools

### Core (all backends)

| Tool | Parameters | Returns |
|---|---|---|
| `list_instances` | — | All configured instances with type and write flags |
| `health_check` | `instance` | Status, version, uptime |
| `query` | `instance, query, params?, limit?` | Rows as list of dicts |
| `schema_inspect` | `instance, table?` | Table/collection list or column details |
| `slow_queries` | `instance, limit?` | Recent slow queries (empty if unsupported) |
| `db_stats` | `instance` | Size, counts, cache ratios |
| `connections` | `instance` | Active sessions and wait states |

### Query formats

| Backend | Format |
|---|---|
| postgresql, clickhouse, mysql, sqlite | SQL string |
| mongodb | JSON: `{"collection": "name", "filter": {}, "projection": {}, "sort": {}}` |
| opensearch | JSON query body; optional `_index` key |
| valkey | Redis command string: `KEYS *`, `GET mykey`, `HGETALL myhash` |
| influxdb | Flux query string |

### Backend-specific extras

**PostgreSQL:** `pg_stat_activity`, `pg_locks`, `autovacuum_status`, `index_usage`, `bloat_estimate`

**ClickHouse:** `ch_query_log(min_duration_ms, limit)`, `ch_parts_info`, `ch_merges`

**MongoDB:** `mongo_current_op`, `mongo_server_status`, `mongo_coll_stats(collection)`, `mongo_index_stats(collection)`

**OpenSearch:** `os_cluster_health`, `os_indices_stats`, `os_shard_allocation`, `os_pending_tasks`

**InfluxDB:** `influx_bucket_list`, `influx_flux_query(flux)`, `influx_write_stats`

**Valkey:** `valkey_server_info`, `valkey_slow_log(limit)`, `valkey_memory_usage(key?)`, `valkey_keyspace_stats`, `valkey_client_list`

**MySQL:** `mysql_processlist`, `mysql_innodb_status`, `mysql_table_stats(schema?)`

## Security model

All backends default to read-only. Write access requires explicit opt-in in config.

### SQL backends (PostgreSQL, ClickHouse, MySQL, SQLite)

Every query is parsed by [sqlglot](https://github.com/tobymao/sqlglot) before execution:

| Statement type | Allowed when |
|---|---|
| `SELECT` | Always |
| `INSERT` / `UPDATE` / `DELETE` | `allow_write = true` |
| `CREATE` / `DROP` / `ALTER` / `TRUNCATE` | `allow_ddl = true` |
| Unclassified (`COPY`, `GRANT`, `CALL`, …) | `allow_ddl = true` |

Data-modifying CTEs (`WITH t AS (DELETE …) SELECT …`) are detected via full AST walk and blocked unless `allow_write = true`.

### Valkey / Redis

Commands are checked against an allowlist before execution. Regardless of `allow_write`, the following commands are always blocked: `EVAL`, `EVALSHA`, `EVAL_RO`, `EVALSHA_RO`, `FCALL`, `FCALL_RO`, `FUNCTION`, `SCRIPT`, `DEBUG`, `SHUTDOWN`, `SLAVEOF`, `REPLICAOF`, `FAILOVER`, `ACL`, `MIGRATE`, `RESTORE`, `CONFIG`.

When `allow_write = false`, only allowlisted read commands (`GET`, `KEYS`, `SCAN`, `INFO`, `HGET`, …) are permitted. Multi-word commands (e.g. `SLOWLOG GET`) enforce subcommand allowlists.

### MongoDB

`$where`, `$function`, and `$accumulator` operators are rejected from all query filters (including nested documents and arrays). Server-side JavaScript evaluation is always blocked.

### InfluxDB

Flux `to()` and `experimental.to()` write sinks are blocked when `allow_write = false`, even if embedded deep in a pipeline. Bucket names are validated against the server's bucket list before string interpolation into Flux queries.

## Deploy with PM2

```bash
# Clone and install
git clone https://github.com/TadMSTR/datastore-mcp.git
cd datastore-mcp
python3 -m venv /opt/venvs/datastore-mcp
/opt/venvs/datastore-mcp/bin/pip install -e ".[all]"

# Place config — ecosystem.config.js points DATASTORE_MCP_CONFIG here
sudo mkdir -p /opt/appdata/datastore-mcp
sudo chown "$USER":"$USER" /opt/appdata/datastore-mcp
touch /opt/appdata/datastore-mcp/config.toml
chmod 600 /opt/appdata/datastore-mcp/config.toml
# Edit with your instances and credentials (see Quick start above)

# Start
pm2 start ecosystem.config.js
pm2 save
```

The shipped `ecosystem.config.js` runs the `/opt/venvs/datastore-mcp` entry point with
`DATASTORE_MCP_CONFIG=/opt/appdata/datastore-mcp/config.toml` and OTLP tracing pointed at
`127.0.0.1:4317`. See [docs/forge.md](docs/forge.md) for the full forge-specific deployment
guide including production instance config and scoped-mcp registration.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATASTORE_MCP_CONFIG` | `~/.config/datastore-mcp/config.toml` | Config file path |
| `LOG_LEVEL` | `INFO` | Logging level (set in `ecosystem.config.js`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | OTLP gRPC trace endpoint; enables tracing (`[telemetry]` extra, or `[all]`) |

## Development

```bash
# Install dev dependencies
pip install -e ".[all]"
pip install pytest pytest-asyncio pytest-cov

# Unit tests (no live DB required)
pytest tests/unit/ --cov=src/datastore_mcp --cov-report=term-missing

# Integration tests (requires sandbox-db stack)
DATASTORE_MCP_INTEGRATION=1 pytest tests/integration/
```

Unit test coverage: 95% (212 tests). The remaining 5% is `create()` classmethods that establish live DB connections, covered by integration tests.

## References

- [AGENTS.md](AGENTS.md) — full tool reference for MCP clients
- [ARCHITECTURE.md](ARCHITECTURE.md) — package layout and request flow
- [docs/forge.md](docs/forge.md) — forge deployment guide
- [CHANGELOG.md](CHANGELOG.md) — release history
