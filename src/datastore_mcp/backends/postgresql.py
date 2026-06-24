"""PostgreSQL backend via asyncpg."""
from __future__ import annotations

from typing import Any

import asyncpg

from datastore_mcp.backends.base import Backend, check_write_safety
from datastore_mcp.config import InstanceConfig


class PostgreSQLBackend(Backend):
    def __init__(self, name: str, cfg: InstanceConfig, pool: asyncpg.Pool) -> None:
        super().__init__(name, cfg)
        self._pool = pool

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> PostgreSQLBackend:
        pool = await asyncpg.create_pool(cfg.url, min_size=1, max_size=5)
        return cls(name, cfg, pool)

    async def close(self) -> None:
        await self._pool.close()

    async def health_check(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version(), pg_postmaster_start_time() AS start_time"
            )
            count = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
        return {
            "status": "ok",
            "version": row["version"],
            "start_time": str(row["start_time"]),
            "connection_count": count,
        }

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        check_write_safety(query, self.cfg, "postgresql")
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *(params or []))
        return [dict(r) for r in rows[:limit]]

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            if table is None:
                rows = await conn.fetch(
                    "SELECT table_schema, table_name, table_type "
                    "FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                    "ORDER BY table_schema, table_name"
                )
                return {"tables": [dict(r) for r in rows]}
            cols = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = $1 ORDER BY ordinal_position",
                table,
            )
            idxs = await conn.fetch(
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = $1",
                table,
            )
            return {
                "table": table,
                "columns": [dict(r) for r in cols],
                "indexes": [dict(r) for r in idxs],
            }

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    "SELECT query, calls, total_exec_time, mean_exec_time, rows "
                    "FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT $1",
                    limit,
                )
                return [dict(r) for r in rows]
            except asyncpg.UndefinedTableError:
                return []

    async def db_stats(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            size = await conn.fetchval(
                "SELECT pg_database_size(current_database())"
            )
            stats = await conn.fetchrow(
                "SELECT sum(n_live_tup) AS live_rows, sum(n_dead_tup) AS dead_rows "
                "FROM pg_stat_user_tables"
            )
            cache = await conn.fetchval(
                "SELECT round(sum(heap_blks_hit)::numeric / "
                "nullif(sum(heap_blks_hit) + sum(heap_blks_read), 0) * 100, 2) "
                "FROM pg_statio_user_tables"
            )
        return {
            "size_bytes": size,
            "live_rows": stats["live_rows"],
            "dead_rows": stats["dead_rows"],
            "cache_hit_pct": float(cache or 0),
        }

    async def connections(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT pid, usename, application_name, state, "
                "wait_event_type, wait_event, query_start "
                "FROM pg_stat_activity WHERE state IS NOT NULL ORDER BY query_start"
            )
        return {"connections": [dict(r) for r in rows]}

    # PostgreSQL-specific extras

    async def pg_stat_activity(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT pid, usename, application_name, client_addr, state, "
                "wait_event_type, wait_event, "
                "now() - query_start AS duration, left(query, 200) AS query "
                "FROM pg_stat_activity WHERE state != 'idle' "
                "ORDER BY duration DESC NULLS LAST"
            )
        return [dict(r) for r in rows]

    async def pg_locks(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT bl.pid AS blocked_pid, a.usename AS blocked_user, "
                "kl.pid AS blocking_pid, ka.usename AS blocking_user, "
                "left(a.query, 200) AS blocked_statement "
                "FROM pg_catalog.pg_locks bl "
                "JOIN pg_catalog.pg_stat_activity a ON a.pid = bl.pid "
                "JOIN pg_catalog.pg_locks kl "
                "  ON kl.transactionid = bl.transactionid AND kl.pid != bl.pid "
                "JOIN pg_catalog.pg_stat_activity ka ON ka.pid = kl.pid "
                "WHERE NOT bl.granted"
            )
        return [dict(r) for r in rows]

    async def autovacuum_status(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT schemaname, relname, n_dead_tup, n_live_tup, "
                "last_autovacuum, last_autoanalyze, autovacuum_count "
                "FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 20"
            )
        return [dict(r) for r in rows]

    async def index_usage(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT schemaname, tablename, indexname, "
                "idx_scan, idx_tup_read, idx_tup_fetch "
                "FROM pg_stat_user_indexes ORDER BY idx_scan ASC LIMIT 20"
            )
        return [dict(r) for r in rows]

    async def bloat_estimate(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            has_ext = await conn.fetchval(
                "SELECT count(*) FROM pg_extension WHERE extname = 'pgstattuple'"
            )
            if not has_ext:
                return [{"note": "pgstattuple extension not installed"}]
            rows = await conn.fetch(
                "SELECT schemaname, tablename, "
                "pg_size_pretty(pg_total_relation_size("
                "  schemaname || '.' || tablename)) AS total_size, "
                "n_dead_tup, n_live_tup "
                "FROM pg_stat_user_tables "
                "WHERE n_dead_tup > 1000 ORDER BY n_dead_tup DESC LIMIT 20"
            )
        return [dict(r) for r in rows]
