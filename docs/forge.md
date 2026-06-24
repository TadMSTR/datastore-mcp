# datastore-mcp on Forge

Port `127.0.0.1:8501`. PM2 process. Config at `/opt/appdata/datastore-mcp/config.toml` (chmod 600).

## Installation

```bash
python3 -m venv /opt/venvs/datastore-mcp
/opt/venvs/datastore-mcp/bin/pip install "datastore-mcp[all]"
```

## PM2 setup

```bash
pm2 start ecosystem.config.js
pm2 save
```

## Config

```bash
sudo mkdir -p /opt/appdata/datastore-mcp
sudo chown ted:ted /opt/appdata/datastore-mcp
touch /opt/appdata/datastore-mcp/config.toml
chmod 600 /opt/appdata/datastore-mcp/config.toml
```

Populate from stack env files (`~/docker/*/docker-compose.yml` + `.env` files).

### Production instance config

```toml
# PostgreSQL instances
[instances.authentik-pg]
type = "postgresql"
url = "postgresql://authentik:PASSWORD@127.0.0.1:5432/authentik"
allow_write = false

[instances.langfuse-pg]
type = "postgresql"
url = "postgresql://langfuse:PASSWORD@127.0.0.1:5433/langfuse"
allow_write = false

[instances.patchmon-pg]
type = "postgresql"
url = "postgresql://patchmon:PASSWORD@127.0.0.1:5434/patchmon"
allow_write = false

# ClickHouse (langfuse analytics)
[instances.langfuse-ch]
type = "clickhouse"
url = "http://127.0.0.1:9000"
user = "default"
password = ""
allow_write = false

# ClickHouse (signoz)
[instances.signoz-ch]
type = "clickhouse"
url = "http://127.0.0.1:9001"
user = "default"
password = ""
allow_write = false

# OpenSearch (memory-stack) — note port 9202, mapped from container 9200
[instances.memory-os]
type = "opensearch"
url = "http://127.0.0.1:9202"
allow_write = false

# InfluxDB (observability) — v2.7
[instances.observability-influxdb]
type = "influxdb"
url = "http://127.0.0.1:8181"
token = "TOKEN_FROM_ENV"
org = "forge"
allow_write = false

# Valkey/Redis instances
[instances.agent-dragonfly]
type = "valkey"
url = "redis://:PASSWORD@127.0.0.1:6380"
allow_write = false

[instances.searxng-dragonfly]
type = "valkey"
url = "redis://:PASSWORD@127.0.0.1:6381"
allow_write = false

# Sandbox (allow_write = true for developer testing)
[instances.sandbox-postgres]
type = "postgresql"
url = "postgresql://sandbox:sandbox@127.0.0.1:15432/sandbox"
allow_write = true

[instances.sandbox-clickhouse]
type = "clickhouse"
url = "http://127.0.0.1:18123"
user = "sandbox"
password = "sandbox"
allow_write = true

[instances.sandbox-mongo]
type = "mongodb"
url = "mongodb://sandbox:sandbox@127.0.0.1:27018/sandbox"
allow_write = true

[instances.sandbox-opensearch]
type = "opensearch"
url = "http://127.0.0.1:19200"
allow_write = true

[instances.sandbox-influxdb]
type = "influxdb"
url = "http://127.0.0.1:18086"
token = "sandbox-token"
org = "sandbox"
bucket = "sandbox"
allow_write = true

[instances.sandbox-valkey]
type = "valkey"
url = "redis://:sandbox@127.0.0.1:16379"
allow_write = true

[instances.sandbox-mysql]
type = "mysql"
url = "mysql://sandbox:sandbox@127.0.0.1:13306/sandbox"
allow_write = true
```

## scoped-mcp registration

```yaml
# ~/.claude/manifests/ — scoped-mcp entries

# sysadmin: all instances, all tools
datastore-mcp-sysadmin:
  url: http://127.0.0.1:8501
  agent: sysadmin
  tools: "*"

# developer: sandbox instances + production read-only core tools
datastore-mcp-developer:
  url: http://127.0.0.1:8501
  agent: developer
  tools: [list_instances, health_check, query, schema_inspect, slow_queries, db_stats, connections]
  # Note: extras not exposed to developer for production instances
```

## Notes

- InfluxDB on forge is v2.7 — uses `influxdb-client` (v2.x API). Flux queries work; SQL interface is InfluxDB 3 only.
- OpenSearch memory-stack is at **port 9202** (mapped from container 9200). Never use 9200 for the forge instance.
- For `bloat_estimate` on production PostgreSQL instances, verify pgstattuple is installed:
  `SELECT * FROM pg_extension WHERE extname = 'pgstattuple';` — the tool returns a note if absent.
- Nextcloud has an internal OpenSearch instance but it's not host-exposed — not configurable here.
