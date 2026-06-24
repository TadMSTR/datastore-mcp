"""MongoDB backend via motor (async)."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from datastore_mcp.backends.base import Backend
from datastore_mcp.config import InstanceConfig


class MongoDBBackend(Backend):
    def __init__(
        self,
        name: str,
        cfg: InstanceConfig,
        client: Any,
        db_name: str,
    ) -> None:
        super().__init__(name, cfg)
        self._client = client
        self._db_name = db_name

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> MongoDBBackend:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(cfg.url)
        parsed = urlparse(cfg.url)
        db_name = parsed.path.lstrip("/") or "test"
        await client.admin.command("ping")
        return cls(name, cfg, client, db_name)

    async def close(self) -> None:
        self._client.close()

    @property
    def _db(self) -> Any:
        return self._client[self._db_name]

    async def health_check(self) -> dict[str, Any]:
        info = await self._client.server_info()
        return {
            "status": "ok",
            "version": info.get("version"),
            "max_wire_version": info.get("maxWireVersion"),
        }

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Query format: JSON object with 'collection', optional 'filter', 'projection', 'sort'."""
        try:
            q = json.loads(query)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"MongoDB query must be a JSON object with a 'collection' key: {exc}"
            ) from exc
        collection_name = q.get("collection")
        if not collection_name:
            raise ValueError("MongoDB query must include 'collection' key")
        filter_doc = q.get("filter", {})
        projection = q.get("projection")
        sort = q.get("sort")
        coll = self._db[collection_name]
        cursor = coll.find(filter_doc, projection)
        if sort:
            cursor = cursor.sort(list(sort.items()))
        cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
        return docs

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        if table is None:
            collections = await self._db.list_collection_names()
            return {"database": self._db_name, "collections": collections}
        coll = self._db[table]
        count = await coll.estimated_document_count()
        sample = await coll.find_one({})
        if sample and "_id" in sample:
            sample["_id"] = str(sample["_id"])
        return {
            "collection": table,
            "estimated_count": count,
            "sample_document": sample,
        }

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        try:
            result = await self._client.admin.command(
                {"currentOp": 1, "secs_running": {"$gte": 1}}
            )
            ops = result.get("inprog", [])[:limit]
            return [
                {
                    "op": o.get("op"),
                    "ns": o.get("ns"),
                    "secs_running": o.get("secs_running"),
                    "desc": o.get("desc"),
                }
                for o in ops
            ]
        except Exception:
            return []

    async def db_stats(self) -> dict[str, Any]:
        stats = await self._db.command("dbStats")
        return {
            "db": stats.get("db"),
            "collections": stats.get("collections"),
            "data_size": stats.get("dataSize"),
            "storage_size": stats.get("storageSize"),
            "index_size": stats.get("indexSize"),
            "objects": stats.get("objects"),
        }

    async def connections(self) -> dict[str, Any]:
        result = await self._client.admin.command("serverStatus")
        conns = result.get("connections", {})
        return {
            "current": conns.get("current"),
            "available": conns.get("available"),
            "total_created": conns.get("totalCreated"),
        }

    # MongoDB-specific extras

    async def current_op(self) -> list[dict[str, Any]]:
        result = await self._client.admin.command({"currentOp": 1})
        ops = result.get("inprog", [])
        return [
            {
                "op": o.get("op"),
                "ns": o.get("ns"),
                "secs_running": o.get("secs_running"),
                "client": o.get("client"),
                "desc": o.get("desc"),
            }
            for o in ops
        ]

    async def server_status(self) -> dict[str, Any]:
        result = await self._client.admin.command("serverStatus")
        return {
            "version": result.get("version"),
            "uptime": result.get("uptime"),
            "connections": result.get("connections"),
            "opcounters": result.get("opcounters"),
            "mem": result.get("mem"),
        }

    async def coll_stats(self, collection: str) -> dict[str, Any]:
        result = await self._db.command("collStats", collection)
        return {
            "ns": result.get("ns"),
            "count": result.get("count"),
            "size": result.get("size"),
            "storage_size": result.get("storageSize"),
            "index_sizes": result.get("indexSizes"),
            "avg_obj_size": result.get("avgObjSize"),
        }

    async def index_stats(self, collection: str) -> list[dict[str, Any]]:
        coll = self._db[collection]
        cursor = coll.aggregate([{"$indexStats": {}}])
        stats = await cursor.to_list(length=None)
        return [
            {"name": s.get("name"), "accesses": s.get("accesses", {}).get("ops", 0)}
            for s in stats
        ]
