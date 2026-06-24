"""Connection pool registry — lazy init, one Backend per named instance."""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from datastore_mcp.backends.base import Backend
    from datastore_mcp.config import DatastoreConfig, InstanceConfig

log = structlog.get_logger()

_BACKEND_MODULES = {
    "postgresql": ("datastore_mcp.backends.postgresql", "PostgreSQLBackend"),
    "clickhouse": ("datastore_mcp.backends.clickhouse", "ClickHouseBackend"),
    "mongodb": ("datastore_mcp.backends.mongodb", "MongoDBBackend"),
    "opensearch": ("datastore_mcp.backends.opensearch", "OpenSearchBackend"),
    "influxdb": ("datastore_mcp.backends.influxdb", "InfluxDBBackend"),
    "valkey": ("datastore_mcp.backends.valkey", "ValkeyBackend"),
    "mysql": ("datastore_mcp.backends.mysql", "MySQLBackend"),
    "sqlite": ("datastore_mcp.backends.sqlite", "SQLiteBackend"),
}


class ConnectionRegistry:
    def __init__(self, config: DatastoreConfig) -> None:
        self._config = config
        self._backends: dict[str, Backend] = {}

    def list_instances(self) -> list[str]:
        return list(self._config.instances.keys())

    def get_config(self, instance: str) -> InstanceConfig:
        if instance not in self._config.instances:
            raise ValueError(
                f"Unknown instance {instance!r}. "
                f"Available: {self.list_instances()}"
            )
        return self._config.instances[instance]

    async def get(self, instance: str) -> Backend:
        if instance not in self._backends:
            cfg = self.get_config(instance)
            log.info("initializing backend", instance=instance, type=cfg.type)
            self._backends[instance] = await _create_backend(instance, cfg)
        return self._backends[instance]

    async def close_all(self) -> None:
        for name, backend in self._backends.items():
            try:
                await backend.close()
            except Exception as exc:
                log.warning("error closing backend", instance=name, error=str(exc))
        self._backends.clear()


async def _create_backend(name: str, cfg: InstanceConfig) -> Backend:
    module_path, class_name = _BACKEND_MODULES[cfg.type]
    try:
        import importlib
        module = importlib.import_module(module_path)
        backend_cls = getattr(module, class_name)
    except ImportError as exc:
        raise ImportError(
            f"Backend library for {cfg.type!r} not installed. "
            f"Run: pip install datastore-mcp[{cfg.type}]"
        ) from exc
    return await backend_cls.create(name, cfg)
