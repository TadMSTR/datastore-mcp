# Changelog

## [Unreleased]

### Added
- Initial release: FastMCP server with health, inspection, and query tools
- 8 backends: PostgreSQL, ClickHouse, MongoDB, OpenSearch, InfluxDB, Valkey/Redis, MySQL, SQLite
- 6 core tools on every backend: list_instances, health_check, query, schema_inspect, slow_queries, db_stats, connections
- Backend-specific extras: pg_stat_activity, pg_locks, autovacuum_status, index_usage, bloat_estimate, ch_query_log, ch_parts_info, ch_merges, mongo_current_op, mongo_server_status, mongo_coll_stats, mongo_index_stats, os_cluster_health, os_indices_stats, os_shard_allocation, os_pending_tasks, influx_bucket_list, influx_flux_query, influx_write_stats, valkey_server_info, valkey_slow_log, valkey_memory_usage, valkey_keyspace_stats, valkey_client_list, mysql_processlist, mysql_innodb_status, mysql_table_stats
- TOML named-instance config with per-instance allow_write and allow_ddl flags
- sqlglot write-safety guard for SQL backends
- structlog JSON logging, OTLP tracing via env var
- PM2 ecosystem config
