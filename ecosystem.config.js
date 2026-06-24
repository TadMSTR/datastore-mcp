module.exports = {
  apps: [{
    name: "datastore-mcp",
    script: "/opt/venvs/datastore-mcp/bin/datastore-mcp",
    env: {
      LOG_LEVEL: "INFO",
      DATASTORE_MCP_CONFIG: "/opt/appdata/datastore-mcp/config.toml",
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://127.0.0.1:4317",
    },
    restart_delay: 5000,
    max_restarts: 10,
  }]
};
