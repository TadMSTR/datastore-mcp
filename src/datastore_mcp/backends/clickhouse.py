"""ClickHouse backend via clickhouse-connect."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from datastore_mcp.backends.base import Backend, check_write_safety
from datastore_mcp.config import InstanceConfig


class ClickHouseBackend(Backend):
    def __init__(self, name: str, cfg: InstanceConfig, client: Any) -> None:
        super().__init__(name, cfg)
        self._client = client

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> ClickHouseBackend:
        import clickhouse_connect

        parsed = urlparse(cfg.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 8123)
        secure = parsed.scheme == "https"
        username = cfg.user or parsed.username or "default"
        password = cfg.password or parsed.password or ""
        client = await clickhouse_connect.get_async_client(
            host=host, port=port, secure=secure,
            username=username, password=password,
        )
        return cls(name, cfg, client)

    async def close(self) -> None:
        await self._client.close()

    async def health_check(self) -> dict[str, Any]:
        result = await self._client.query(
            "SELECT version() AS version, uptime() AS uptime_seconds"
        )
        row = result.first_row
        return {"status": "ok", "version": row[0], "uptime_seconds": row[1]}

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        check_write_safety(query, self.cfg, "clickhouse")
        result = await self._client.query(query)
        rows = [
            dict(zip(result.column_names, row))
            for row in result.result_rows
        ]
        return rows[:limit]

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        if table is None:
            result = await self._client.query(
                "SELECT database, name, engine "
                "FROM system.tables WHERE database != 'system' "
                "ORDER BY database, name"
            )
            return {
                "tables": [
                    {"database": r[0], "name": r[1], "engine": r[2]}
                    for r in result.result_rows
                ]
            }
        result = await self._client.query(
            "SELECT name, type, default_kind, default_expression "
            "FROM system.columns WHERE table = {table:String}",
            parameters={"table": table},
        )
        return {
            "table": table,
            "columns": [
                {"name": r[0], "type": r[1], "default_kind": r[2], "default": r[3]}
                for r in result.result_rows
            ],
        }

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        result = await self._client.query(
            f"SELECT query, query_duration_ms, read_rows, read_bytes, memory_usage "
            f"FROM system.query_log WHERE type = 'QueryFinish' "
            f"AND query_duration_ms > 1000 "
            f"ORDER BY query_duration_ms DESC LIMIT {limit}"
        )
        return [dict(zip(result.column_names, r)) for r in result.result_rows]

    async def db_stats(self) -> dict[str, Any]:
        result = await self._client.query(
            "SELECT database, "
            "sum(bytes_on_disk) AS bytes_on_disk, sum(rows) AS rows "
            "FROM system.parts WHERE active GROUP BY database"
        )
        return {
            "databases": [
                {"database": r[0], "bytes_on_disk": r[1], "rows": r[2]}
                for r in result.result_rows
            ]
        }

    async def connections(self) -> dict[str, Any]:
        result = await self._client.query(
            "SELECT query_id, user, elapsed, memory_usage, left(query, 200) AS query "
            "FROM system.processes ORDER BY elapsed DESC"
        )
        return {"processes": [dict(zip(result.column_names, r)) for r in result.result_rows]}

    # ClickHouse-specific extras

    async def query_log(
        self, min_duration_ms: int = 1000, limit: int = 20
    ) -> list[dict[str, Any]]:
        result = await self._client.query(
            f"SELECT event_time, query_duration_ms, read_rows, read_bytes, "
            f"result_rows, memory_usage, left(query, 200) AS query "
            f"FROM system.query_log WHERE type = 'QueryFinish' "
            f"AND query_duration_ms >= {min_duration_ms} "
            f"ORDER BY event_time DESC LIMIT {limit}"
        )
        return [dict(zip(result.column_names, r)) for r in result.result_rows]

    async def parts_info(self) -> list[dict[str, Any]]:
        result = await self._client.query(
            "SELECT database, table, count() AS part_count, "
            "sum(rows) AS rows, sum(bytes_on_disk) AS bytes_on_disk, "
            "sum(data_compressed_bytes) AS compressed_bytes "
            "FROM system.parts WHERE active "
            "GROUP BY database, table ORDER BY bytes_on_disk DESC"
        )
        return [dict(zip(result.column_names, r)) for r in result.result_rows]

    async def merges(self) -> list[dict[str, Any]]:
        result = await self._client.query(
            "SELECT database, table, merge_type, elapsed, progress, "
            "num_parts, rows_read, rows_written FROM system.merges "
            "ORDER BY elapsed DESC"
        )
        return [dict(zip(result.column_names, r)) for r in result.result_rows]
