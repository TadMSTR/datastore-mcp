"""Unit tests for TOML config loading and validation."""
import pathlib
import tempfile
import textwrap

import pytest

from datastore_mcp.config import DatastoreConfig, InstanceConfig, load_config


def _write_toml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False, encoding="utf-8"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


class TestInstanceConfig:
    def test_defaults(self):
        cfg = InstanceConfig(type="postgresql", url="postgresql://localhost/test")
        assert cfg.allow_write is False
        assert cfg.allow_ddl is False
        assert cfg.user is None

    def test_allow_write(self):
        cfg = InstanceConfig(
            type="postgresql", url="postgresql://localhost/test", allow_write=True
        )
        assert cfg.allow_write is True

    def test_extra_fields_pass_through(self):
        cfg = InstanceConfig(
            type="clickhouse",
            url="http://localhost:8123",
            user="sandbox",
            password="s3cret",
        )
        assert cfg.user == "sandbox"
        assert cfg.password == "s3cret"

    def test_influxdb_fields(self):
        cfg = InstanceConfig(
            type="influxdb",
            url="http://localhost:8086",
            token="my-token",
            org="myorg",
            bucket="mybucket",
        )
        assert cfg.token == "my-token"
        assert cfg.org == "myorg"
        assert cfg.bucket == "mybucket"

    def test_invalid_type_rejected(self):
        with pytest.raises(Exception):
            InstanceConfig(type="oracle", url="jdbc://localhost")

    @pytest.mark.parametrize("btype", [
        "postgresql", "clickhouse", "mongodb", "opensearch",
        "influxdb", "valkey", "mysql", "sqlite",
    ])
    def test_all_backend_types_valid(self, btype):
        cfg = InstanceConfig(type=btype, url="proto://localhost")
        assert cfg.type == btype


class TestLoadConfig:
    def test_load_multiple_instances(self):
        path = _write_toml("""
            [instances.pg1]
            type = "postgresql"
            url = "postgresql://localhost/db1"

            [instances.pg2]
            type = "postgresql"
            url = "postgresql://localhost/db2"
            allow_write = true
        """)
        cfg = load_config(path)
        assert "pg1" in cfg.instances
        assert "pg2" in cfg.instances
        assert cfg.instances["pg1"].allow_write is False
        assert cfg.instances["pg2"].allow_write is True

    def test_load_mixed_backends(self):
        path = _write_toml("""
            [instances.db-pg]
            type = "postgresql"
            url = "postgresql://localhost/test"

            [instances.db-redis]
            type = "valkey"
            url = "redis://localhost:6379"
        """)
        cfg = load_config(path)
        assert cfg.instances["db-pg"].type == "postgresql"
        assert cfg.instances["db-redis"].type == "valkey"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.toml")

    def test_env_var_override(self, monkeypatch, tmp_path):
        toml = tmp_path / "test.toml"
        toml.write_text(
            '[instances.x]\ntype = "sqlite"\nurl = "file:/tmp/x.db"\n'
        )
        monkeypatch.setenv("DATASTORE_MCP_CONFIG", str(toml))
        cfg = load_config()
        assert "x" in cfg.instances
