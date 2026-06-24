"""Unit tests for SQL write-safety classification and enforcement."""
import pytest

from datastore_mcp.backends.base import _classify_sql, check_write_safety
from datastore_mcp.config import InstanceConfig


def _cfg(allow_write=False, allow_ddl=False, btype="postgresql"):
    return InstanceConfig(type=btype, url="postgresql://localhost/test",
                          allow_write=allow_write, allow_ddl=allow_ddl)


class TestClassifySql:
    @pytest.mark.parametrize("sql", [
        "SELECT 1",
        "SELECT * FROM foo WHERE id = 1",
        "SELECT a, b FROM t JOIN u ON t.id = u.t_id",
        "WITH cte AS (SELECT 1) SELECT * FROM cte",
    ])
    def test_select_classified(self, sql):
        assert _classify_sql(sql, "postgres") == "select"

    @pytest.mark.parametrize("sql", [
        "INSERT INTO foo VALUES (1)",
        "UPDATE foo SET a = 1",
        "DELETE FROM foo WHERE id = 1",
    ])
    def test_dml_classified(self, sql):
        assert _classify_sql(sql, "postgres") == "dml"

    @pytest.mark.parametrize("sql", [
        "CREATE TABLE foo (id INT)",
        "DROP TABLE foo",
        "ALTER TABLE foo ADD COLUMN bar TEXT",
        "TRUNCATE TABLE foo",
    ])
    def test_ddl_classified(self, sql):
        result = _classify_sql(sql, "postgres")
        assert result == "ddl"

    def test_clickhouse_dialect(self):
        assert _classify_sql("SELECT 1", "clickhouse") == "select"

    def test_mysql_dialect(self):
        assert _classify_sql("SELECT 1", "mysql") == "select"

    def test_sqlite_dialect(self):
        assert _classify_sql("SELECT 1", "sqlite") == "select"


class TestCheckWriteSafety:
    def test_select_always_allowed(self):
        cfg = _cfg(allow_write=False)
        check_write_safety("SELECT 1", cfg, "postgresql")  # no exception

    def test_dml_blocked_by_default(self):
        cfg = _cfg(allow_write=False)
        with pytest.raises(PermissionError, match="Write statements"):
            check_write_safety("DELETE FROM foo", cfg, "postgresql")

    def test_dml_allowed_with_flag(self):
        cfg = _cfg(allow_write=True)
        check_write_safety("DELETE FROM foo WHERE id = 1", cfg, "postgresql")

    def test_ddl_blocked_even_with_write(self):
        cfg = _cfg(allow_write=True, allow_ddl=False)
        with pytest.raises(PermissionError, match="DDL"):
            check_write_safety("DROP TABLE foo", cfg, "postgresql")

    def test_ddl_allowed_with_flag(self):
        cfg = _cfg(allow_write=True, allow_ddl=True)
        check_write_safety("CREATE TABLE foo (id INT)", cfg, "postgresql")

    def test_ddl_blocked_when_only_write_allowed(self):
        cfg = _cfg(allow_write=True, allow_ddl=False)
        with pytest.raises(PermissionError):
            check_write_safety("ALTER TABLE foo ADD COLUMN x TEXT", cfg, "postgresql")

    def test_insert_blocked_default(self):
        cfg = _cfg()
        with pytest.raises(PermissionError):
            check_write_safety("INSERT INTO foo VALUES (1)", cfg, "postgresql")

    def test_update_blocked_default(self):
        cfg = _cfg()
        with pytest.raises(PermissionError):
            check_write_safety("UPDATE foo SET x = 1 WHERE id = 1", cfg, "postgresql")

    # H-1: data-modifying CTEs must be classified as dml, not select
    @pytest.mark.parametrize("sql", [
        "WITH t AS (DELETE FROM x RETURNING *) SELECT * FROM t",
        "WITH t AS (INSERT INTO x VALUES (1) RETURNING *) SELECT * FROM t",
        "WITH t AS (UPDATE x SET a=1 RETURNING *) SELECT * FROM t",
    ])
    def test_writable_cte_classified_as_dml(self, sql):
        assert _classify_sql(sql, "postgres") == "dml"

    @pytest.mark.parametrize("sql", [
        "WITH t AS (DELETE FROM x RETURNING *) SELECT * FROM t",
        "WITH t AS (INSERT INTO x VALUES (1) RETURNING *) SELECT * FROM t",
    ])
    def test_writable_cte_blocked_on_readonly_instance(self, sql):
        cfg = _cfg(allow_write=False)
        with pytest.raises(PermissionError, match="Write statements"):
            check_write_safety(sql, cfg, "postgresql")

    # M-1: "other" statements blocked unless allow_ddl=true
    def test_other_blocked_without_allow_ddl(self):
        # CALL is classified as "other" by sqlglot
        cfg = _cfg(allow_write=True, allow_ddl=False)
        with pytest.raises(PermissionError, match="allow_ddl"):
            check_write_safety("CALL myfunc()", cfg, "postgresql")

    def test_other_allowed_with_allow_ddl(self):
        cfg = _cfg(allow_write=True, allow_ddl=True)
        check_write_safety("CALL myfunc()", cfg, "postgresql")  # no exception
