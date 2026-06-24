"""Shared pytest configuration."""
import os
import pathlib
import pytest


SANDBOX_TOML = pathlib.Path(__file__).parent / "sandbox.toml"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires DATASTORE_MCP_INTEGRATION=1 and sandbox-db stack",
    )


def pytest_collection_modifyitems(config, items):
    if not os.getenv("DATASTORE_MCP_INTEGRATION"):
        skip = pytest.mark.skip(reason="set DATASTORE_MCP_INTEGRATION=1 to run")
        for item in items:
            if "integration" in item.nodeid:
                item.add_marker(skip)
