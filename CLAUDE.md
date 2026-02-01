# PriceAgent - Development Guidelines

## Git Workflow

### Branching Strategy
- **`development`** - All new features, changes, and bug fixes go here first
- **`main`** - Production-ready code only (merge via `deploy_to_prod.sh`)

### Commit Rules
Every change must be committed separately with a descriptive message:

```
<type>: <user instruction summary>

<description of the solution>
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

**IMPORTANT: Commit Frequently**
- Commit after every logical change, not at the end of a session
- Each feature, fix, or improvement should be its own commit
- Do not batch multiple unrelated changes into one commit
- Push to git after each commit to ensure work is saved

**Example:**
```
feat: Add bulk WhatsApp messaging with editable templates

Integrated DraftModal and useDraftStore from dashboard into landing page.
Users can now select multiple sellers and edit message templates before
sending. Added phone number enrichment from sellers database.
```

### Deployment Process

1. **Development deployment** (`./deploy.sh`):
   - Runs all tests (pytest + frontend tests)
   - Commits to `development` branch
   - Only succeeds if all tests pass

2. **Production deployment** (`./deploy_to_prod.sh`):
   - **USER ONLY** - Claude should never run this
   - Merges `development` into `main`
   - Tags the release
   - Deploys to production

---

## Testing Requirements

### Every code change MUST include tests
- New features: Add unit tests + integration tests
- Bug fixes: Add regression test that would have caught the bug
- Refactors: Ensure existing tests still pass, add tests for edge cases

### Test Structure
```
tests/
├── unit/           # Fast, isolated tests
├── e2e/            # End-to-end tests
└── conftest.py     # Shared fixtures
```

### Running Tests
```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=src --cov-report=html
```

---

## Code Architecture

### Extensibility Principles

**For custom use cases (e.g., different seller websites, scraping methods):**

1. **Create separate files** - One file per implementation
2. **Use registry pattern** - Register implementations, avoid switch/case
3. **Minimize coupling** - Each implementation should be self-contained
4. **Easy extension** - Adding new sellers should only require adding a new file

**Example - Scraper Architecture:**
```
src/scrapers/
├── base.py              # Abstract base class
├── registry.py          # Scraper registry (auto-discovery)
├── zap_scraper.py       # Zap.co.il implementation
├── google_scraper.py    # Google Shopping implementation
└── wisebuy_scraper.py   # Wisebuy implementation
```

**Registry Pattern:**
```python
# registry.py
SCRAPERS: Dict[str, Type[BaseScraper]] = {}

def register(domain: str):
    def decorator(cls):
        SCRAPERS[domain] = cls
        return cls
    return decorator

def get_scraper(domain: str) -> BaseScraper:
    return SCRAPERS.get(domain, DefaultScraper)()

# zap_scraper.py
@register("zap.co.il")
class ZapScraper(BaseScraper):
    ...
```

**Avoid this:**
```python
# BAD - switch/case for use cases
if domain == "zap.co.il":
    scraper = ZapScraper()
elif domain == "wisebuy.co.il":
    scraper = WisebuyScraper()
else:
    scraper = DefaultScraper()
```

---

## Logging Requirements

### What to Log

1. **User interactions** - All searches, seller contacts, selections
2. **Service calls** - API requests, external service calls
3. **Errors** - All exceptions with stack traces
4. **Performance** - Request durations, slow operations

### Logger Configuration

The logger must be configurable for different environments:

```python
# config.py
class LogConfig:
    # Development: local file/console
    # Production: external service (e.g., Datadog, CloudWatch)

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")  # json or text
    LOG_DESTINATION: str = os.getenv("LOG_DESTINATION", "local")  # local or external
    EXTERNAL_LOG_ENDPOINT: str = os.getenv("LOG_ENDPOINT", "")
```

**Environment Examples:**
```bash
# Development
LOG_LEVEL=DEBUG
LOG_FORMAT=text
LOG_DESTINATION=local

# Production
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_DESTINATION=external
LOG_ENDPOINT=https://logs.example.com/ingest
```

### Logging Usage
```python
from src.logging import get_logger

logger = get_logger(__name__)

# User interaction
logger.info("user_search", query=query, user_id=user_id)

# Service call
logger.info("api_call", service="zap", endpoint="/search", duration_ms=150)

# Error
logger.error("scrape_failed", url=url, error=str(e), exc_info=True)
```

---

## Project Structure

```
/Users/yonigo/my_agent/
├── src/                    # Python backend
│   ├── api/               # FastAPI routes
│   ├── agents/            # AI agents
│   ├── scrapers/          # Web scrapers (extensible)
│   ├── db/                # Database models and repos
│   ├── observability/     # Tracing and monitoring
│   └── logging/           # Configurable logging
├── frontend/              # Next.js frontend
│   ├── src/app/          # Pages
│   ├── src/components/   # React components
│   ├── src/stores/       # Zustand stores
│   └── src/lib/          # Utilities
├── tests/                 # Test suite
│   ├── unit/
│   └── e2e/
├── deploy.sh              # Deploy to development
├── deploy_to_prod.sh      # Deploy to production (USER ONLY)
└── run.sh                 # Run locally
```

---

## Key Conventions

- **Language**: Hebrew for user-facing messages, English for code/logs
- **Phone numbers**: Always include country code (+972)
- **State management**: Zustand for React, no Redux
- **API client**: Use `frontend/src/lib/api.ts` for all backend calls
- **Styling**: Tailwind CSS, dark theme
- **Database**: SQLite with SQLAlchemy async
