# Security

## Credential handling

- Connection strings live in `config.toml` (chmod 600, owner-only).
- No per-instance env vars — one file, one place.
- Credentials are never returned to callers, logged, or included in OTLP spans.
- Consider encrypting `config.toml` at rest with sops/age for additional hardening.

## Write safety

- `allow_write = false` (default) blocks INSERT, UPDATE, DELETE, MERGE via sqlglot.
- `allow_ddl = false` (default) blocks CREATE, DROP, ALTER, TRUNCATE — separate flag.
- MongoDB queries use Python dicts, not string parsing — no SQL injection surface.
- OpenSearch queries are validated as JSON objects — no string concatenation.
- Redis/Valkey: write commands are blocked via a static allowlist of mutating commands.
- InfluxDB Flux queries are inherently read-only on the query API path.

## Network binding

- Binds to `127.0.0.1` only — not exposed to external networks.
- Access controlled at the scoped-mcp layer (per-agent instance restrictions).

## Reporting vulnerabilities

Open an issue at https://github.com/TadMSTR/datastore-mcp/issues with the label `security`.
