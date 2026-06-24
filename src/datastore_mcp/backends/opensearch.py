"""OpenSearch backend via opensearch-py (async)."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from datastore_mcp.backends.base import Backend
from datastore_mcp.config import InstanceConfig


class OpenSearchBackend(Backend):
    def __init__(self, name: str, cfg: InstanceConfig, client: Any) -> None:
        super().__init__(name, cfg)
        self._client = client

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> OpenSearchBackend:
        from opensearchpy import AsyncOpenSearch

        parsed = urlparse(cfg.url)
        host = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 9200,
            "use_ssl": parsed.scheme == "https",
        }
        http_auth = None
        if parsed.username:
            http_auth = (parsed.username, parsed.password or "")
        client = AsyncOpenSearch(
            hosts=[host],
            http_auth=http_auth,
            verify_certs=False,
            ssl_show_warn=False,
        )
        return cls(name, cfg, client)

    async def close(self) -> None:
        await self._client.close()

    async def health_check(self) -> dict[str, Any]:
        info = await self._client.info()
        return {
            "status": "ok",
            "version": info["version"]["number"],
            "cluster_name": info["cluster_name"],
        }

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Query format: JSON body with optional '_index' key for the target index."""
        try:
            body = json.loads(query)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenSearch query must be a JSON object: {exc}") from exc
        index = body.pop("_index", "_all")
        if "size" not in body:
            body["size"] = limit
        result = await self._client.search(index=index, body=body)
        hits = result["hits"]["hits"]
        return [{"_id": h["_id"], "_index": h["_index"], **h.get("_source", {})} for h in hits]

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        if table is None:
            result = await self._client.cat.indices(
                format="json",
                h="index,health,status,docs.count,store.size",
            )
            return {"indices": result}
        mapping = await self._client.indices.get_mapping(index=table)
        return {"index": table, "mapping": mapping}

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        # OpenSearch exposes slow queries in tasks API
        tasks = await self._client.tasks.list()
        found = []
        for node_info in tasks.get("nodes", {}).values():
            for task_id, task in node_info.get("tasks", {}).items():
                found.append({
                    "task_id": task_id,
                    "action": task.get("action"),
                    "running_time_ms": task.get("running_time_in_nanos", 0) // 1_000_000,
                })
        return sorted(found, key=lambda x: -x["running_time_ms"])[:limit]

    async def db_stats(self) -> dict[str, Any]:
        stats = await self._client.cluster.stats()
        return {
            "indices_count": stats["indices"]["count"],
            "total_docs": stats["indices"]["docs"]["count"],
            "store_size_bytes": stats["indices"]["store"]["size_in_bytes"],
            "nodes": stats["nodes"]["count"]["total"],
        }

    async def connections(self) -> dict[str, Any]:
        stats = await self._client.nodes.stats(metric="transport")
        return {
            "nodes": {
                k: v.get("transport", {})
                for k, v in stats["nodes"].items()
            }
        }

    # OpenSearch-specific extras

    async def cluster_health(self) -> dict[str, Any]:
        return await self._client.cluster.health()

    async def indices_stats(self) -> list[dict[str, Any]]:
        return await self._client.cat.indices(format="json")

    async def shard_allocation(self) -> list[dict[str, Any]]:
        return await self._client.cat.shards(format="json")

    async def pending_tasks(self) -> list[dict[str, Any]]:
        result = await self._client.cluster.pending_tasks()
        return result.get("tasks", [])
