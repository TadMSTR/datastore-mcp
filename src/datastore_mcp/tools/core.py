"""Core 6-tool interface — uniform across all backends."""
from __future__ import annotations

from typing import Any


def register_core_tools(mcp: Any, registry: Any) -> None:
    @mcp.tool()
    async def list_instances() -> list[dict[str, Any]]:
        """List all configured datastore instances with their type and write permissions."""
        return [
            {
                "instance": name,
                "type": registry.get_config(name).type,
                "allow_write": registry.get_config(name).allow_write,
            }
            for name in registry.list_instances()
        ]

    @mcp.tool()
    async def health_check(instance: str) -> dict[str, Any]:
        """Ping, version, and connection count for a named datastore instance."""
        backend = await registry.get(instance)
        return await backend.health_check()

    @mcp.tool()
    async def query(
        instance: str,
        query: str,
        params: list | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Execute a read query against a named datastore instance.

        SQL backends: standard SQL SELECT statement.
        MongoDB: JSON object — {"collection": "name", "filter": {}, "projection": {}, "sort": {}}.
        OpenSearch: JSON query body with optional "_index" key.
        Redis/Valkey: raw command string e.g. "KEYS *" or "GET mykey".
        InfluxDB: Flux query string.
        Write statements are blocked unless allow_write = true in config.
        """
        backend = await registry.get(instance)
        return await backend.query(query, params=params, limit=limit)

    @mcp.tool()
    async def schema_inspect(
        instance: str, table: str | None = None
    ) -> dict[str, Any]:
        """Inspect schema for a named datastore instance.

        Without 'table': lists all tables/collections/indices.
        With 'table': describes columns, types, and indexes for that object.
        OpenSearch: 'table' is an index name.
        Redis/Valkey: 'table' is a key pattern for SCAN.
        """
        backend = await registry.get(instance)
        return await backend.schema_inspect(table=table)

    @mcp.tool()
    async def slow_queries(
        instance: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Recent slow queries from the instance's query log or stats tables.

        Returns empty list if the backend doesn't support slow query logging
        (InfluxDB, SQLite, connections-only backends).
        """
        backend = await registry.get(instance)
        return await backend.slow_queries(limit=limit)

    @mcp.tool()
    async def db_stats(instance: str) -> dict[str, Any]:
        """Size on disk, row/document counts, cache hit ratio, and backend stats."""
        backend = await registry.get(instance)
        return await backend.db_stats()

    @mcp.tool()
    async def connections(instance: str) -> dict[str, Any]:
        """Active sessions, wait states, and lock waits for a named instance."""
        backend = await registry.get(instance)
        return await backend.connections()
