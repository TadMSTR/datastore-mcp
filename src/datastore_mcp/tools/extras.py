"""Backend-specific extra tools, registered per instance type."""
from __future__ import annotations

from typing import Any

from opentelemetry import trace

_tracer = trace.get_tracer("datastore-mcp")


def _span(tool_name: str, instance: str, backend_type: str):
    span = _tracer.start_span(tool_name)
    span.set_attribute("db.instance", instance)
    span.set_attribute("db.system", backend_type)
    span.set_attribute("mcp.tool", tool_name)
    return trace.use_span(span, end_on_exit=True)


def _type_check(backend: Any, expected: str, instance: str) -> None:
    if backend.cfg.type != expected:
        raise ValueError(
            f"Instance {instance!r} is type {backend.cfg.type!r}, not {expected!r}"
        )


def register_extra_tools(mcp: Any, registry: Any) -> None:

    # ── PostgreSQL ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def pg_stat_activity(instance: str) -> list[dict[str, Any]]:
        """PostgreSQL active queries, wait events, idle-in-transaction sessions."""
        b = await registry.get(instance)
        _type_check(b, "postgresql", instance)
        with _span("pg_stat_activity", instance, "postgresql"):
            return await b.pg_stat_activity()

    @mcp.tool()
    async def pg_locks(instance: str) -> list[dict[str, Any]]:
        """PostgreSQL lock waits and blocking queries."""
        b = await registry.get(instance)
        _type_check(b, "postgresql", instance)
        with _span("pg_locks", instance, "postgresql"):
            return await b.pg_locks()

    @mcp.tool()
    async def autovacuum_status(instance: str) -> list[dict[str, Any]]:
        """Tables with dead tuple accumulation and autovacuum history."""
        b = await registry.get(instance)
        _type_check(b, "postgresql", instance)
        with _span("autovacuum_status", instance, "postgresql"):
            return await b.autovacuum_status()

    @mcp.tool()
    async def index_usage(instance: str) -> list[dict[str, Any]]:
        """PostgreSQL index scan counts — identifies unused indexes."""
        b = await registry.get(instance)
        _type_check(b, "postgresql", instance)
        with _span("index_usage", instance, "postgresql"):
            return await b.index_usage()

    @mcp.tool()
    async def bloat_estimate(instance: str) -> list[dict[str, Any]]:
        """Table and index bloat estimate. Requires pgstattuple extension."""
        b = await registry.get(instance)
        _type_check(b, "postgresql", instance)
        with _span("bloat_estimate", instance, "postgresql"):
            return await b.bloat_estimate()

    # ── ClickHouse ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def ch_query_log(
        instance: str, min_duration_ms: int = 1000, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Recent ClickHouse queries from system.query_log, filterable by duration."""
        b = await registry.get(instance)
        _type_check(b, "clickhouse", instance)
        with _span("ch_query_log", instance, "clickhouse"):
            return await b.query_log(min_duration_ms=min_duration_ms, limit=limit)

    @mcp.tool()
    async def ch_parts_info(instance: str) -> list[dict[str, Any]]:
        """ClickHouse system.parts — part counts and compression ratios per table."""
        b = await registry.get(instance)
        _type_check(b, "clickhouse", instance)
        with _span("ch_parts_info", instance, "clickhouse"):
            return await b.parts_info()

    @mcp.tool()
    async def ch_merges(instance: str) -> list[dict[str, Any]]:
        """In-progress ClickHouse merges from system.merges."""
        b = await registry.get(instance)
        _type_check(b, "clickhouse", instance)
        with _span("ch_merges", instance, "clickhouse"):
            return await b.merges()

    # ── MongoDB ─────────────────────────────────────────────────────────────

    @mcp.tool()
    async def mongo_current_op(instance: str) -> list[dict[str, Any]]:
        """MongoDB running operations and long-running query detection."""
        b = await registry.get(instance)
        _type_check(b, "mongodb", instance)
        with _span("mongo_current_op", instance, "mongodb"):
            return await b.current_op()

    @mcp.tool()
    async def mongo_server_status(instance: str) -> dict[str, Any]:
        """MongoDB serverStatus — connections, opcounters, memory."""
        b = await registry.get(instance)
        _type_check(b, "mongodb", instance)
        with _span("mongo_server_status", instance, "mongodb"):
            return await b.server_status()

    @mcp.tool()
    async def mongo_coll_stats(
        instance: str, collection: str
    ) -> dict[str, Any]:
        """MongoDB collection stats — size, index count, avg document size."""
        b = await registry.get(instance)
        _type_check(b, "mongodb", instance)
        with _span("mongo_coll_stats", instance, "mongodb"):
            return await b.coll_stats(collection)

    @mcp.tool()
    async def mongo_index_stats(
        instance: str, collection: str
    ) -> list[dict[str, Any]]:
        """MongoDB index usage counts via $indexStats."""
        b = await registry.get(instance)
        _type_check(b, "mongodb", instance)
        with _span("mongo_index_stats", instance, "mongodb"):
            return await b.index_stats(collection)

    # ── OpenSearch ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def os_cluster_health(instance: str) -> dict[str, Any]:
        """OpenSearch cluster health — status, shard counts, unassigned."""
        b = await registry.get(instance)
        _type_check(b, "opensearch", instance)
        with _span("os_cluster_health", instance, "opensearch"):
            return await b.cluster_health()

    @mcp.tool()
    async def os_indices_stats(instance: str) -> list[dict[str, Any]]:
        """OpenSearch _cat/indices — doc counts, store size, health per index."""
        b = await registry.get(instance)
        _type_check(b, "opensearch", instance)
        with _span("os_indices_stats", instance, "opensearch"):
            return await b.indices_stats()

    @mcp.tool()
    async def os_shard_allocation(instance: str) -> list[dict[str, Any]]:
        """OpenSearch _cat/shards — shard distribution and unassigned reasons."""
        b = await registry.get(instance)
        _type_check(b, "opensearch", instance)
        with _span("os_shard_allocation", instance, "opensearch"):
            return await b.shard_allocation()

    @mcp.tool()
    async def os_pending_tasks(instance: str) -> list[dict[str, Any]]:
        """OpenSearch cluster pending tasks."""
        b = await registry.get(instance)
        _type_check(b, "opensearch", instance)
        with _span("os_pending_tasks", instance, "opensearch"):
            return await b.pending_tasks()

    # ── InfluxDB ────────────────────────────────────────────────────────────

    @mcp.tool()
    async def influx_bucket_list(instance: str) -> list[dict[str, Any]]:
        """List InfluxDB buckets with retention policies."""
        b = await registry.get(instance)
        _type_check(b, "influxdb", instance)
        with _span("influx_bucket_list", instance, "influxdb"):
            return await b.bucket_list()

    @mcp.tool()
    async def influx_flux_query(instance: str, flux: str) -> list[dict[str, Any]]:
        """Execute a Flux query against InfluxDB (always read-only)."""
        b = await registry.get(instance)
        _type_check(b, "influxdb", instance)
        with _span("influx_flux_query", instance, "influxdb"):
            return await b.flux_query(flux)

    @mcp.tool()
    async def influx_write_stats(instance: str) -> list[dict[str, Any]]:
        """Points written per bucket from _monitoring bucket (last 1h)."""
        b = await registry.get(instance)
        _type_check(b, "influxdb", instance)
        with _span("influx_write_stats", instance, "influxdb"):
            return await b.write_stats()

    # ── Valkey/Redis ────────────────────────────────────────────────────────

    @mcp.tool()
    async def valkey_server_info(instance: str) -> dict[str, Any]:
        """Valkey/Redis INFO all — version, memory, clients, keyspace."""
        b = await registry.get(instance)
        _type_check(b, "valkey", instance)
        with _span("valkey_server_info", instance, "valkey"):
            return await b.server_info()

    @mcp.tool()
    async def valkey_slow_log(
        instance: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Valkey/Redis SLOWLOG GET — recent slow commands."""
        b = await registry.get(instance)
        _type_check(b, "valkey", instance)
        with _span("valkey_slow_log", instance, "valkey"):
            return await b.slow_log(limit=limit)

    @mcp.tool()
    async def valkey_memory_usage(
        instance: str, key: str | None = None
    ) -> dict[str, Any]:
        """MEMORY USAGE for a specific key, or MEMORY DOCTOR for overall analysis."""
        b = await registry.get(instance)
        _type_check(b, "valkey", instance)
        with _span("valkey_memory_usage", instance, "valkey"):
            return await b.memory_usage(key=key)

    @mcp.tool()
    async def valkey_keyspace_stats(instance: str) -> dict[str, Any]:
        """Key counts and TTL distribution per Redis database."""
        b = await registry.get(instance)
        _type_check(b, "valkey", instance)
        with _span("valkey_keyspace_stats", instance, "valkey"):
            return await b.keyspace_stats()

    @mcp.tool()
    async def valkey_client_list(instance: str) -> list[dict[str, Any]]:
        """Active Valkey/Redis client connections."""
        b = await registry.get(instance)
        _type_check(b, "valkey", instance)
        with _span("valkey_client_list", instance, "valkey"):
            return await b.client_list()

    # ── MySQL/MariaDB ───────────────────────────────────────────────────────

    @mcp.tool()
    async def mysql_processlist(instance: str) -> list[dict[str, Any]]:
        """MySQL/MariaDB SHOW FULL PROCESSLIST."""
        b = await registry.get(instance)
        _type_check(b, "mysql", instance)
        with _span("mysql_processlist", instance, "mysql"):
            return await b.processlist()

    @mcp.tool()
    async def mysql_innodb_status(instance: str) -> dict[str, Any]:
        """MySQL SHOW ENGINE INNODB STATUS. Requires PROCESS privilege."""
        b = await registry.get(instance)
        _type_check(b, "mysql", instance)
        with _span("mysql_innodb_status", instance, "mysql"):
            return await b.innodb_status()

    @mcp.tool()
    async def mysql_table_stats(
        instance: str, schema: str | None = None
    ) -> list[dict[str, Any]]:
        """MySQL table sizes and row counts from information_schema."""
        b = await registry.get(instance)
        _type_check(b, "mysql", instance)
        with _span("mysql_table_stats", instance, "mysql"):
            return await b.table_stats(schema=schema)
