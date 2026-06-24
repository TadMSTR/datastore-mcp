# Contributing

## Development setup

```bash
git clone https://github.com/TadMSTR/datastore-mcp.git
cd datastore-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
pip install pytest pytest-asyncio pytest-cov
```

## Running tests

```bash
# Unit tests only
pytest tests/unit/

# Integration tests (requires sandbox-db stack)
DATASTORE_MCP_INTEGRATION=1 pytest tests/integration/

# Full suite with coverage
pytest tests/unit/ --cov=src --cov-report=term-missing
```

## Adding a backend

1. Create `src/datastore_mcp/backends/<name>.py` implementing `Backend`.
2. Register it in `registry.py` `_BACKEND_MODULES` dict.
3. Add to `BackendType` Literal in `config.py`.
4. Add optional dependency group in `pyproject.toml`.
5. Add core tool tests in `tests/integration/test_<name>.py`.
6. Document in `docs/forge.md` if applicable.

## Code style

- Python 3.11+, type annotations throughout
- `structlog` for logging — never log credentials or query params
- OTLP spans: instance name, backend type, tool name — never auth fields
