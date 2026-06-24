"""InfluxDB backend via influxdb-client (v2.x API).

Forge runs InfluxDB 2.7. Uses influxdb-client (not influxdb3-python).
InfluxDBClientAsync only exposes query_api(). Bucket/org operations use httpx
against the REST API directly.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

# Flux write functions that must be blocked on read-only instances (M-3a).
_FLUX_WRITE_PATTERN = re.compile(r"\|>\s*(?:experimental\.)?to\s*\(", re.IGNORECASE)

from datastore_mcp.backends.base import Backend
from datastore_mcp.config import InstanceConfig


class InfluxDBBackend(Backend):
    def __init__(
        self,
        name: str,
        cfg: InstanceConfig,
        client: Any,
        http: httpx.AsyncClient,
    ) -> None:
        super().__init__(name, cfg)
        self._client = client
        self._http = http
        self._org = cfg.org or "default"
        self._token = cfg.token or ""
        self._default_bucket = cfg.bucket

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._token}"}

    @classmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> InfluxDBBackend:
        from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

        token = cfg.token or ""
        org = cfg.org or "default"
        client = InfluxDBClientAsync(url=cfg.url, token=token, org=org)
        http = httpx.AsyncClient(base_url=cfg.url, headers={"Authorization": f"Token {token}"})
        return cls(name, cfg, client, http)

    async def close(self) -> None:
        await self._client.close()
        await self._http.aclose()

    async def health_check(self) -> dict[str, Any]:
        ping = await self._client.ping()
        version = await self._client.version()
        return {
            "status": "pass" if ping else "error",
            "version": version,
        }

    def _check_flux_write(self, flux: str) -> None:
        """Raise PermissionError if the Flux query contains a write sink (M-3a)."""
        if not self.cfg.allow_write and _FLUX_WRITE_PATTERN.search(flux):
            raise PermissionError(
                "Flux query contains a write operation (to() / experimental.to()). "
                "Set allow_write = true in config to enable Flux writes."
            )

    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Execute a Flux query."""
        self._check_flux_write(query)
        query_api = self._client.query_api()
        tables = await query_api.query(query, org=self._org)
        rows = []
        for table in tables:
            for record in table.records:
                rows.append(record.values)
        return rows[:limit]

    async def schema_inspect(self, table: str | None = None) -> dict[str, Any]:
        buckets = await self._list_buckets()
        if table:
            bucket_names = {b["name"] for b in buckets}
            if table not in bucket_names:
                raise ValueError(
                    f"Unknown bucket: {table!r}. "
                    f"Known buckets: {sorted(bucket_names)}"
                )
            query_api = self._client.query_api()
            # table is validated against the server's bucket list before interpolation (M-3b)
            flux = (
                f'import "influxdata/influxdb/schema"\n'
                f'schema.measurements(bucket: "{table}")'
            )
            try:
                tables_result = await query_api.query(flux, org=self._org)
                measurements = [
                    r.get_value()
                    for t in tables_result
                    for r in t.records
                ]
                return {"bucket": table, "measurements": measurements}
            except Exception as exc:
                return {"bucket": table, "error": str(exc)}
        return {"buckets": buckets}

    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        return []  # InfluxDB 2.x does not expose slow query log via API

    async def db_stats(self) -> dict[str, Any]:
        buckets = await self._list_buckets()
        return {"bucket_count": len(buckets), "org": self._org}

    async def connections(self) -> dict[str, Any]:
        return {}  # InfluxDB 2.x does not expose connection tracking

    # Internal helpers

    async def _list_buckets(self) -> list[dict[str, Any]]:
        r = await self._http.get("/api/v2/buckets", params={"org": self._org})
        r.raise_for_status()
        data = r.json()
        return [
            {
                "name": b["name"],
                "id": b["id"],
                "retention_rules": b.get("retentionRules", []),
            }
            for b in data.get("buckets", [])
        ]

    # InfluxDB-specific extras

    async def bucket_list(self) -> list[dict[str, Any]]:
        return await self._list_buckets()

    async def flux_query(self, flux: str) -> list[dict[str, Any]]:
        self._check_flux_write(flux)
        query_api = self._client.query_api()
        tables = await query_api.query(flux, org=self._org)
        return [r.values for t in tables for r in t.records]

    async def write_stats(self) -> list[dict[str, Any]]:
        flux = (
            'from(bucket: "_monitoring")\n'
            "  |> range(start: -1h)\n"
            '  |> filter(fn: (r) => r._measurement == "batcher")\n'
            '  |> filter(fn: (r) => r._field == "writeOk")\n'
            '  |> group(columns: ["bucket"])\n'
            "  |> sum()"
        )
        try:
            query_api = self._client.query_api()
            tables = await query_api.query(flux, org=self._org)
            return [r.values for t in tables for r in t.records]
        except Exception:
            return []
