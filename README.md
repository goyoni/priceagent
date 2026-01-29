# My Agent

A product research agent that finds best purchase options across price comparison sites.

## Setup

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Agent

```bash
python -m src.main
```

## Testing

### Run Tests (Replay Mode)

Uses recorded cassettes - no API calls, no credits consumed:

```bash
pytest tests/e2e/ -v
```

### Record New Cassettes

Records fresh responses from real APIs. **This consumes API credits!**

```bash
python tests/record_cassettes.py
```

### Run Tests in Record Mode

Records cassettes during test execution:

```bash
pytest tests/e2e/ -v --record
```

## Caching

The agent includes a two-tier caching system (LRU memory + SQLite persistence) with version-based invalidation.

- **Scraper results**: Cached for 24 hours
- **Contact info**: Cached for 7 days
- **Agent tool results**: Cached for 24 hours

Cache is automatically invalidated when source code changes.

### Bypass Cache

Use `no_cache=True` parameter to bypass cache for specific calls:

```python
result = await search_products("query", no_cache=True)
```

## Observability

Tool call spans include cache status (`cached: true/false`) for visibility into cache hits/misses in traces.
