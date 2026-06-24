"""Abstract Backend interface and SQL write-safety guard."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import sqlglot
import sqlglot.expressions as exp

if TYPE_CHECKING:
    from datastore_mcp.config import InstanceConfig

# Dialect names that sqlglot uses for each backend type
_DIALECTS: dict[str, str] = {
    "postgresql": "postgres",
    "clickhouse": "clickhouse",
    "mysql": "mysql",
    "sqlite": "sqlite",
}

SQL_BACKENDS = frozenset(_DIALECTS)


def _classify_sql(sql: str, dialect: str) -> str:
    """Return 'select', 'dml', 'ddl', or 'other' for a SQL statement."""
    try:
        stmt = sqlglot.parse_one(sql.strip(), dialect=dialect or None)
    except Exception:
        return "other"
    if isinstance(stmt, exp.Select):
        return "select"
    if isinstance(stmt, exp.With):
        # CTE — inspect the final statement
        inner = stmt.this
        return "select" if isinstance(inner, exp.Select) else "dml"
    if isinstance(stmt, (exp.Insert, exp.Update, exp.Delete, exp.Merge)):
        return "dml"
    if isinstance(stmt, (exp.Create, exp.Drop, exp.Alter, exp.TruncateTable)):
        return "ddl"
    return "other"


def check_write_safety(sql: str, cfg: InstanceConfig, backend_type: str) -> None:
    """Raise PermissionError if the query is blocked by instance write rules."""
    dialect = _DIALECTS.get(backend_type, "")
    stmt_type = _classify_sql(sql, dialect)
    if stmt_type == "ddl" and not cfg.allow_ddl:
        raise PermissionError(
            f"DDL statements are blocked for this instance. "
            f"Set allow_ddl = true in config to enable."
        )
    if stmt_type in ("dml",) and not cfg.allow_write:
        raise PermissionError(
            f"Write statements (INSERT/UPDATE/DELETE) are blocked for this instance. "
            f"Set allow_write = true in config to enable."
        )
    if stmt_type == "other" and not cfg.allow_write:
        raise PermissionError(
            f"Statement type could not be classified as read-only. "
            f"Set allow_write = true in config to permit it."
        )


class Backend(ABC):
    """Abstract base class for all datastore backends."""

    def __init__(self, name: str, cfg: InstanceConfig) -> None:
        self.name = name
        self.cfg = cfg

    @classmethod
    @abstractmethod
    async def create(cls, name: str, cfg: InstanceConfig) -> Backend: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    async def query(
        self, query: str, params: list | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def schema_inspect(
        self, table: str | None = None
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def slow_queries(self, limit: int = 10) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def db_stats(self) -> dict[str, Any]: ...

    @abstractmethod
    async def connections(self) -> dict[str, Any]: ...
