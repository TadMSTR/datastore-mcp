# AGENTS.md — datastore-mcp

Multi-backend database MCP server. FastMCP. Port 8501.

## Tools

### Core (all backends)

| Tool | Parameters | Returns |
|---|---|---|
| `list_instances` | — | List of configured instances with type and write flag |
| `health_check` | `instance` | Status, version, connection count |
| `query` | `instance, query, params?, limit?` | Rows as list of dicts |
| `schema_inspect` | `instance, table?` | Table list or column/index details |
| `slow_queries` | `instance, limit?` | Recent slow queries (empty if unsupported) |
| `db_stats` | `instance` | Size, row counts, cache hit ratio |
| `connections` | `instance` | Active sessions and wait states |

### Query formats by backend

| Backend | Query format |
|---|---|
| postgresql, clickhouse, mysql, sqlite | SQL string |
| mongodb | JSON: `{"collection": "name", "filter": {}, "projection": {}, "sort": {}}` |
| opensearch | JSON query body; optional `_index` key for target index |
| valkey | Redis command string e.g. `KEYS *` or `GET mykey` |
| influxdb | Flux query string |

### Backend-specific extras

**PostgreSQL:** `pg_stat_activity`, `pg_locks`, `autovacuum_status`, `index_usage`, `bloat_estimate`

**ClickHouse:** `ch_query_log(min_duration_ms, limit)`, `ch_parts_info`, `ch_merges`

**MongoDB:** `mongo_current_op`, `mongo_server_status`, `mongo_coll_stats(collection)`, `mongo_index_stats(collection)`

**OpenSearch:** `os_cluster_health`, `os_indices_stats`, `os_shard_allocation`, `os_pending_tasks`

**InfluxDB:** `influx_bucket_list`, `influx_flux_query(flux)`, `influx_write_stats`

**Valkey:** `valkey_server_info`, `valkey_slow_log(limit)`, `valkey_memory_usage(key?)`, `valkey_keyspace_stats`, `valkey_client_list`

**MySQL:** `mysql_processlist`, `mysql_innodb_status`, `mysql_table_stats(schema?)`

## Config

```toml
[instances.my-pg]
type = "postgresql"
url = "postgresql://user:pass@host:5432/db"
allow_write = false   # default

[instances.my-ch]
type = "clickhouse"
url = "http://host:8123"
user = "default"
password = ""
allow_write = false
```

Set `DATASTORE_MCP_CONFIG=/path/to/config.toml` or use default `~/.config/datastore-mcp/config.toml`.

## Write safety

SQL backends: sqlglot parses every query before execution.
- SELECT → always allowed
- INSERT/UPDATE/DELETE → blocked unless `allow_write = true`
- CREATE/DROP/ALTER → blocked unless `allow_ddl = true`

Non-SQL backends enforce write safety at the command/API level.

## Notes

- Backends lazy-initialize on first use. Cold start may add ~100ms for pool creation.
- InfluxDB: forge runs v2.7. Flux queries work; SQL interface requires InfluxDB 3.
- Valkey: fully Redis-protocol-compatible. Use `redis://` or `valkey://` URLs.
- SQLite: no concurrent connection pool — each query opens/closes the file.
