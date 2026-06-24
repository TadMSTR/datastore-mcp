"""Valkey/Redis backend via redis-py (async).

Valkey is Redis-protocol-compatible. redis-py works without modification.
Configure with a redis:// or valkey:// URL.
"""
from __future__ import annotations

from typing import Any

from datastore_mcp.backends.base import Backend
from datastore_mcp.config import InstanceConfig

_WRITE_COMMANDS = frozenset({
    "SET", "SETEX", "SETNX", "MSET", "MSETNX", "GETSET",
    "DEL", "UNLINK", "EXPIRE", "EXPIREAT", "PEXPIRE", "PEXPIREAT", "PERSIST",
    "RENAME", "RENAMENX", "MOVE", "COPY",
    "APPEND", "INCR", "INCRBY", "INCRBYFLOAT", "DECR", "DECRBY",
    "HSET", "HMSET", "HSETNX", "HDEL", "HINCRBY", "HINCRBYFLOAT",
    "LPUSH", "RPUSH", "LPUSHX", "RPUSHX", "LINSERT", "LSET", "LREM", "LTRIM",
    "LPOP", "RPOP", "RPOPLPUSH", "LMOVE",
    "SADD", "SREM", "SMOVE", "SPOP",
    "ZADD", "ZREM", "ZINCRBY", "ZREMRANGEBYRANK", "ZREMRANGEBYSCORE", "ZREMRANGEBYLEX",
    "XADD", "XDEL", "XTRIM",
    "FLUSHDB", "FLUSHALL", "SWAPDB",
})


class ValkeyBackend(Backend):
    def __init__(self, name: str, cfg: InstanceConfig, client: Any) -> None:
        super().__init__(name, cfg)
        self._client = client

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> ValkeyBackend:
        import redis.asyncio as aioredis

        url = cfg.url.replace("valkey://", "redis://")
        client = aioredis.from_url(url, decode_responses=True)
        await client.ping()
        return cls(name, cfg, client)

    async def close(self) -> None:
        await self._client.aclose()

    async def health_check(self) -> dict[str, Any]:
        info = await self._client.info("server")
        ping = await self._client.ping()
        return {
            "status": "ok" if ping else "error",
            "redis_version": info.get("redis_version"),
            "uptime_in_seconds": info.get("uptime_in_seconds"),
        }

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Execute a Redis command string (e.g. 'KEYS *' or 'GET mykey')."""
        parts = query.strip().split()
        if not parts:
            raise ValueError("Empty command")
        cmd = parts[0].upper()
        if not self.cfg.allow_write and cmd in _WRITE_COMMANDS:
            raise PermissionError(
                f"Write command {cmd!r} blocked. "
                f"Set allow_write = true in config to enable."
            )
        args = parts[1:]
        result = await self._client.execute_command(cmd, *args)
        if isinstance(result, list):
            return [{"value": v} for v in result[:limit]]
        return [{"value": result}]

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        info = await self._client.info("keyspace")
        keyspace = {k: v for k, v in info.items() if k.startswith("db")}
        if table:
            cursor = 0
            keys: list[str] = []
            while True:
                cursor, batch = await self._client.scan(
                    cursor=cursor, match=table, count=100
                )
                keys.extend(batch)
                if cursor == 0 or len(keys) >= 100:
                    break
            return {"pattern": table, "matching_keys": keys[:100]}
        return {"keyspace": keyspace}

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        entries = await self._client.slowlog_get(limit)
        return [
            {"id": e["id"], "duration_us": e["duration"], "command": e["command"]}
            for e in entries
        ]

    async def db_stats(self) -> dict[str, Any]:
        info = await self._client.info("all")
        return {
            "used_memory_human": info.get("used_memory_human"),
            "total_commands_processed": info.get("total_commands_processed"),
            "connected_clients": info.get("connected_clients"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }

    async def connections(self) -> dict[str, Any]:
        clients = await self._client.client_list()
        return {"clients": clients[:50]}

    # Valkey-specific extras

    async def server_info(self) -> dict[str, Any]:
        return await self._client.info("all")

    async def slow_log(self, limit: int = 10) -> list[dict[str, Any]]:
        entries = await self._client.slowlog_get(limit)
        return [
            {"id": e["id"], "duration_us": e["duration"], "command": e["command"]}
            for e in entries
        ]

    async def memory_usage(self, key: str | None = None) -> dict[str, Any]:
        if key:
            usage = await self._client.memory_usage(key)
            return {"key": key, "bytes": usage}
        doctor = await self._client.execute_command("MEMORY DOCTOR")
        return {"doctor": doctor}

    async def keyspace_stats(self) -> dict[str, Any]:
        info = await self._client.info("keyspace")
        return {k: v for k, v in info.items() if k.startswith("db")}

    async def client_list(self) -> list[dict[str, Any]]:
        return await self._client.client_list()
