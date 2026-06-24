"""Shared fixtures for integration tests against sandbox-db stack."""
import pathlib

import pytest
import pytest_asyncio

from datastore_mcp.config import load_config
from datastore_mcp.registry import ConnectionRegistry

SANDBOX_TOML = pathlib.Path(__file__).parent.parent / "sandbox.toml"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def registry():
    cfg = load_config(str(SANDBOX_TOML))
    reg = ConnectionRegistry(cfg)
    yield reg
    await reg.close_all()
