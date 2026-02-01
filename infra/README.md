# Logging Infrastructure

This directory contains configuration for the production logging stack using Grafana Loki.

## Quick Start

### 1. Start the logging stack

```bash
cd infra
docker-compose -f docker-compose.logging.yml up -d
```

### 2. Configure PriceAgent

Add to your `.env` or environment:

```bash
# Enable external logging
LOG_EXTERNAL_ENABLED=true
LOG_EXTERNAL_ENDPOINT=http://localhost:3100/loki/api/v1/push
LOG_EXTERNAL_LABELS='{"app":"priceagent","env":"development"}'

# Optional: adjust log level
LOG_LEVEL=INFO
```

### 3. Access Grafana

- URL: http://localhost:3001
- Username: `admin`
- Password: `admin`

The "PriceAgent Logs" dashboard is automatically provisioned.

## Components

### Loki
- **Port**: 3100
- Log aggregation service
- Stores logs for 7 days (configurable)
- Optimized for high-volume log ingestion

### Grafana
- **Port**: 3001
- Visualization and querying
- Pre-configured Loki datasource
- PriceAgent dashboard included

## LogQL Queries

```logql
# All logs
{app="priceagent"}

# Filter by level
{app="priceagent"} |= "error"
{app="priceagent"} | json | level="ERROR"

# Filter by environment
{app="priceagent", env="production"}

# Search for text
{app="priceagent"} |= "product_discovery"

# Parse JSON and filter
{app="priceagent"} | json | event="api_request" | duration > 1000

# Count errors per minute
count_over_time({app="priceagent"} |= "error" [1m])

# Client-side logs
{app="priceagent", source="frontend"}

# Trace correlation
{app="priceagent"} | json | trace_id="abc123"
```

## Production Deployment

For production, consider:

1. **External Loki/Grafana**: Use managed services (Grafana Cloud, AWS, etc.)
2. **Authentication**: Enable Grafana auth, disable anonymous access
3. **Retention**: Adjust `retention_period` in loki-config.yml
4. **Scaling**: Use object storage (S3, GCS) instead of filesystem

### Production environment variables

```bash
ENVIRONMENT=production
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_TO_FILE=true
LOG_EXTERNAL_ENABLED=true
LOG_EXTERNAL_ENDPOINT=https://logs.example.com/loki/api/v1/push
LOG_EXTERNAL_LABELS='{"app":"priceagent","env":"production","region":"us-east-1"}'
```

## Troubleshooting

### Logs not appearing in Grafana

1. Check Loki is healthy: `curl http://localhost:3100/ready`
2. Verify logs are being sent: check `logs/app.log` for Loki errors
3. Check labels match: `{app="priceagent"}` requires matching label in LOG_EXTERNAL_LABELS

### High memory usage

Adjust Loki limits in `loki/loki-config.yml`:
- Reduce `ingestion_rate_mb`
- Lower `max_entries_limit_per_query`

### Dashboard not loading

1. Check Grafana logs: `docker-compose logs grafana`
2. Verify provisioning files are mounted correctly
3. Manually import dashboard from JSON if needed
