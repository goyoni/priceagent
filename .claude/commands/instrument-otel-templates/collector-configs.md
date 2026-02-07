# OTEL Collector Configuration Templates

Reference configurations for the OpenTelemetry Collector and visualization backends.

---

## Base Collector Config (Jaeger Backend)

`otel-collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins: ["*"]
          allowed_headers: ["*"]

processors:
  batch:
    timeout: 5s
    send_batch_size: 512
    send_batch_max_size: 1024

  memory_limiter:
    check_interval: 5s
    limit_mib: 256
    spike_limit_mib: 64

exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

  debug:
    verbosity: basic

service:
  telemetry:
    logs:
      level: info

  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger, debug]
```

---

## Docker Compose — Jaeger (Default)

`docker-compose.otel.yaml`:

```yaml
version: "3.8"

services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver
    depends_on:
      - jaeger
    restart: unless-stopped

  jaeger:
    image: jaegertracing/jaeger:latest
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686" # Jaeger UI
      - "4317"        # OTLP gRPC (internal only)
    restart: unless-stopped
```

---

## Docker Compose — Grafana Tempo

For Tempo + Grafana visualization:

```yaml
version: "3.8"

services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4317:4317"
      - "4318:4318"
    depends_on:
      - tempo
    restart: unless-stopped

  tempo:
    image: grafana/tempo:latest
    command: ["-config.file=/etc/tempo/tempo.yaml"]
    volumes:
      - ./tempo-config.yaml:/etc/tempo/tempo.yaml:ro
      - tempo-data:/var/tempo
    ports:
      - "3200:3200"   # Tempo HTTP API
      - "4317"        # OTLP gRPC (internal)
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    ports:
      - "3001:3000"   # Grafana UI (3001 to avoid conflicts)
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana-datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml:ro
    depends_on:
      - tempo
    restart: unless-stopped

volumes:
  tempo-data:
  grafana-data:
```

### Tempo Config

`tempo-config.yaml`:

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317

storage:
  trace:
    backend: local
    local:
      path: /var/tempo/traces
    wal:
      path: /var/tempo/wal

query_frontend:
  search:
    max_duration: 0
```

### Grafana Datasource

`grafana-datasources.yaml`:

```yaml
apiVersion: 1

datasources:
  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    isDefault: true
    version: 1
    editable: false
```

### Collector Config for Tempo

Replace the exporter section:

```yaml
exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/tempo, debug]
```

---

## Collector Config — Honeycomb

```yaml
exporters:
  otlp/honeycomb:
    endpoint: "api.honeycomb.io:443"
    headers:
      "x-honeycomb-team": "${env:HONEYCOMB_API_KEY}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/honeycomb]
```

---

## Collector Config — Datadog

```yaml
exporters:
  datadog:
    api:
      key: "${env:DD_API_KEY}"
      site: "${env:DD_SITE}"  # e.g., datadoghq.com

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [datadog]
```

---

## Collector Config — Console (Development)

For development without any backend — just log to console:

```yaml
exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

---

## Collector Config — Multiple Backends

Export to multiple backends simultaneously:

```yaml
exporters:
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

  otlp/honeycomb:
    endpoint: "api.honeycomb.io:443"
    headers:
      "x-honeycomb-team": "${env:HONEYCOMB_API_KEY}"

  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger, otlp/honeycomb, debug]
```

---

## Environment Variables Template

`.env.otel.example`:

```bash
# ==========================================
# OpenTelemetry Configuration
# ==========================================

# Kill switch — set to "false" to disable all telemetry
OTEL_ENABLED=true

# Service identification
OTEL_SERVICE_NAME=my-service
OTEL_SERVICE_VERSION=0.1.0
DEPLOYMENT_ENVIRONMENT=development

# OTLP exporter endpoint (gRPC)
# For local collector:
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# For Honeycomb direct (no collector):
# OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io

# Sampling (parentbased_always_on = sample everything)
# For production, consider: parentbased_traceidratio
OTEL_TRACES_SAMPLER=parentbased_always_on
# OTEL_TRACES_SAMPLER_ARG=0.1  # Sample 10% (for traceidratio)

# ==========================================
# Frontend OTEL (browser → collector via HTTP)
# ==========================================
NEXT_PUBLIC_OTEL_ENDPOINT=http://localhost:4318/v1/traces
NEXT_PUBLIC_OTEL_SERVICE_NAME=my-frontend

# ==========================================
# Backend-specific (optional)
# ==========================================

# Honeycomb (if exporting directly, not via collector)
# HONEYCOMB_API_KEY=your-api-key-here

# Datadog (if using Datadog exporter)
# DD_API_KEY=your-api-key-here
# DD_SITE=datadoghq.com
```

---

## Startup Script

`otel-up.sh`:

```bash
#!/bin/bash
set -e

# Start OTEL Collector + visualization backend for local development
echo "Starting OTEL infrastructure..."

docker-compose -f docker-compose.otel.yaml up -d

echo ""
echo "==================================="
echo "  OTEL Infrastructure Running"
echo "==================================="
echo ""
echo "  OTLP gRPC:  localhost:4317"
echo "  OTLP HTTP:  localhost:4318"
echo "  Jaeger UI:  http://localhost:16686"
echo ""
echo "  To stop: docker-compose -f docker-compose.otel.yaml down"
echo ""
```

Make executable: `chmod +x otel-up.sh`

---

## Shutdown Script

`otel-down.sh`:

```bash
#!/bin/bash
# Stop OTEL infrastructure
docker-compose -f docker-compose.otel.yaml down
echo "OTEL infrastructure stopped."
```

---

## Health Check

To verify the collector is running and accepting data:

```bash
# Check collector health
curl -s http://localhost:4318/v1/traces -X POST \
  -H "Content-Type: application/json" \
  -d '{}' && echo "Collector is accepting HTTP traces"

# Check Jaeger has data
curl -s http://localhost:16686/api/services | jq '.data'
```

---

## Production Considerations

1. **Sampling**: In production, don't sample 100% of traces. Use `parentbased_traceidratio` with a ratio like 0.1 (10%).

2. **Memory limits**: The `memory_limiter` processor prevents the collector from using too much memory. Adjust `limit_mib` based on your infrastructure.

3. **Batch size**: The `batch` processor batches spans before export. Larger batches are more efficient but add latency. The defaults (5s timeout, 512 batch size) work well for most cases.

4. **TLS**: In production, enable TLS between your app and the collector, and between the collector and the backend. Remove `insecure: true`.

5. **Resource detection**: Consider adding resource detection processors to automatically capture cloud metadata:
   ```yaml
   processors:
     resourcedetection:
       detectors: [env, system, docker, gcp, aws, azure]
   ```

6. **Tail sampling**: For high-throughput services, use tail-based sampling to keep all error traces while sampling normal traces:
   ```yaml
   processors:
     tail_sampling:
       decision_wait: 10s
       policies:
         - name: errors
           type: status_code
           status_code: {status_codes: [ERROR]}
         - name: normal
           type: probabilistic
           probabilistic: {sampling_percentage: 10}
   ```
