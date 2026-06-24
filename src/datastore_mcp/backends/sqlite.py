"""SQLite backend via aiosqlite."""
from __future__ import annotations

import os
from typing import Any

import aiosqlite

from datastore_mcp.backends.base import Backend, check_write_safety
from datastore_mcp.config import InstanceConfig


class SQLiteBackend(Backend):
    def __init__(self, name: str, cfg: InstanceConfig, db_path: str) -> None:
        super().__init__(name, cfg)
        self._db_path = db_path

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> SQLiteBackend:
        db_path = (
            cfg.url
            .removeprefix("sqlite:///")
            .removeprefix("sqlite://")
            .removeprefix("file:")
        )
        backend = cls(name, cfg, db_path)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("SELECT 1")
        return backend

    async def close(self) -> None:
        pass  # aiosqlite opens/closes per operation

    async def health_check(self) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT sqlite_version()") as cur:
                row = await cur.fetchone()
            async with db.execute("PRAGMA integrity_check") as cur:
                check = await cur.fetchone()
        return {"status": "ok", "version": row[0], "integrity": check[0]}

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        check_write_safety(query, self.cfg, "sqlite")
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params or ()) as cur:
                rows = await cur.fetchmany(limit)
        return [dict(r) for r in rows]

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if table is None:
                async with db.execute(
                    "SELECT name, type FROM sqlite_master "
                    "WHERE type IN ('table', 'view') ORDER BY name"
                ) as cur:
                    rows = await cur.fetchall()
                return {"objects": [dict(r) for r in rows]}
            async with db.execute(f"PRAGMA table_info({table})") as cur:
                cols = await cur.fetchall()
            async with db.execute(f"PRAGMA index_list({table})") as cur:
                idxs = await cur.fetchall()
            return {
                "table": table,
                "columns": [dict(c) for c in cols],
                "indexes": [dict(i) for i in idxs],
            }

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        return []  # SQLite has no slow query log

    async def db_stats(self) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("PRAGMA page_count") as cur:
                page_count = (await cur.fetchone())[0]
            async with db.execute("PRAGMA page_size") as cur:
                page_size = (await cur.fetchone())[0]
            async with db.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ) as cur:
                table_count = (await cur.fetchone())[0]
        file_size = (
            os.path.getsize(self._db_path) if os.path.exists(self._db_path) else 0
        )
        return {
            "file_size_bytes": file_size,
            "db_size_bytes": page_count * page_size,
            "page_count": page_count,
            "page_size": page_size,
            "table_count": table_count,
        }

    async def connections(self) -> dict[str, Any]:
        return {"note": "SQLite does not support concurrent connections"}
