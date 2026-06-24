"""MySQL/MariaDB backend via aiomysql."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import aiomysql

from datastore_mcp.backends.base import Backend, check_write_safety
from datastore_mcp.config import InstanceConfig


class MySQLBackend(Backend):
    def __init__(self, name: str, cfg: InstanceConfig, pool: Any) -> None:
        super().__init__(name, cfg)
        self._pool = pool

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> MySQLBackend:
        parsed = urlparse(cfg.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3306
        user = parsed.username or "root"
        password = parsed.password or ""
        db = parsed.path.lstrip("/") or None
        pool = await aiomysql.create_pool(
            host=host, port=port, user=user, password=password,
            db=db, minsize=1, maxsize=5, autocommit=True,
        )
        return cls(name, cfg, pool)

    async def close(self) -> None:
        self._pool.close()
        await self._pool.wait_closed()

    async def health_check(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT VERSION(), CONNECTION_ID()")
                row = await cur.fetchone()
        return {"status": "ok", "version": row[0], "connection_id": row[1]}

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        check_write_safety(query, self.cfg, "mysql")
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params or ())
                rows = await cur.fetchmany(limit)
        return list(rows)

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if table is None:
                    await cur.execute(
                        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ENGINE, TABLE_ROWS "
                        "FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA NOT IN "
                        "  ('information_schema', 'performance_schema', 'mysql', 'sys')"
                    )
                    rows = await cur.fetchall()
                    return {"tables": list(rows)}
                await cur.execute(
                    "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
                    "COLUMN_DEFAULT, COLUMN_KEY "
                    "FROM information_schema.COLUMNS "
                    "WHERE TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                    (table,),
                )
                cols = await cur.fetchall()
                return {"table": table, "columns": list(cols)}

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute(
                        "SELECT query_time, lock_time, rows_sent, rows_examined, sql_text "
                        f"FROM mysql.slow_log ORDER BY query_time DESC LIMIT {limit}"
                    )
                    rows = await cur.fetchall()
                    return list(rows)
                except Exception:
                    return []

    async def db_stats(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT TABLE_SCHEMA, "
                    "SUM(DATA_LENGTH + INDEX_LENGTH) AS total_size, "
                    "SUM(TABLE_ROWS) AS total_rows "
                    "FROM information_schema.TABLES GROUP BY TABLE_SCHEMA"
                )
                rows = await cur.fetchall()
        return {"databases": list(rows)}

    async def connections(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SHOW FULL PROCESSLIST")
                rows = await cur.fetchall()
        return {"processes": list(rows)}

    # MySQL-specific extras

    async def processlist(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SHOW FULL PROCESSLIST")
                rows = await cur.fetchall()
        return list(rows)

    async def innodb_status(self) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                try:
                    await cur.execute("SHOW ENGINE INNODB STATUS")
                    row = await cur.fetchone()
                    return {"status": row["Status"]} if row else {}
                except Exception as exc:
                    return {"error": str(exc), "note": "PROCESS privilege required"}

    async def table_stats(self, schema: str | None = None) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if schema:
                    await cur.execute(
                        "SELECT TABLE_NAME, ENGINE, TABLE_ROWS, "
                        "DATA_LENGTH, INDEX_LENGTH "
                        "FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = %s ORDER BY DATA_LENGTH DESC",
                        (schema,),
                    )
                else:
                    await cur.execute(
                        "SELECT TABLE_SCHEMA, TABLE_NAME, ENGINE, "
                        "TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH "
                        "FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA NOT IN "
                        "  ('information_schema', 'performance_schema', 'mysql', 'sys') "
                        "ORDER BY DATA_LENGTH DESC LIMIT 50"
                    )
                rows = await cur.fetchall()
        return list(rows)
