"""TOML config loader with pydantic validation."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

DEFAULT_CONFIG_PATH = "~/.config/datastore-mcp/config.toml"

BackendType = Literal[
    "postgresql", "clickhouse", "mongodb", "opensearch",
    "influxdb", "valkey", "mysql", "sqlite",
]


class InstanceConfig(BaseModel):
    """Named datastore instance configuration.

    Extra fields (user, password, token, org, bucket) are passed through
    as-is to support backend-specific connection parameters.
    """
    model_config = ConfigDict(extra="allow")

    type: BackendType
    url: str
    allow_write: bool = False
    allow_ddl: bool = False

    # ClickHouse — optional separate auth
    user: str | None = None
    password: str | None = None

    # InfluxDB — org, token, default bucket
    token: str | None = None
    org: str | None = None
    bucket: str | None = None


class DatastoreConfig(BaseModel):
    instances: dict[str, InstanceConfig]


def load_config(path: str | None = None) -> DatastoreConfig:
    resolved = Path(
        path or os.getenv("DATASTORE_MCP_CONFIG", DEFAULT_CONFIG_PATH)
    ).expanduser()
    with open(resolved, "rb") as f:
        raw = tomllib.load(f)
    return DatastoreConfig(**raw)
