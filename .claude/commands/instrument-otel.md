# /instrument-otel — Add OpenTelemetry Observability to Any Project

You are an expert observability engineer. Your task is to add comprehensive OpenTelemetry (OTEL) instrumentation to this codebase. Follow each phase in order. Be thorough but non-destructive — never remove existing code, only add instrumentation alongside it.

**Argument handling:** The user may pass an optional scope argument: `$ARGUMENTS`
- If empty or "all" → Run all phases (1–5)
- If "backend" → Run phases 1 + 2 only
- If "frontend" → Run phases 1 + 3 only
- If "agents" → Run phases 1 + 4 only
- If "collector" → Run phases 1 + 5 only

---

## Phase 1: Detection — Analyze the Tech Stack

Scan the project to identify the tech stack. Read key files to determine what's in use. Report findings before proceeding.

### Step 1.1: Identify project files

Search for these files to determine the stack:

**Python indicators:**
- `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`, `Pipfile`, `poetry.lock`
- `*.py` files in `src/`, `app/`, or root

**Node.js indicators:**
- `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
- `tsconfig.json`, `*.ts`, `*.tsx` files

**Go indicators:**
- `go.mod`, `go.sum`
- `*.go` files

### Step 1.2: Detect frameworks and libraries

Read dependency files and scan imports to identify:

| Category | What to look for |
|---|---|
| **Backend framework** | FastAPI, Flask, Django, Express, Koa, Hapi, Gin, Echo, Fiber |
| **Frontend framework** | Next.js, React, Vue, Svelte, Angular |
| **Agent/AI framework** | `openai-agents`, `langchain`, `crewai`, `autogen`, `llama-index`, custom agent loops |
| **Database** | SQLAlchemy, Prisma, TypeORM, Sequelize, GORM, raw SQL drivers |
| **HTTP clients** | httpx, requests, urllib3, axios, fetch, node-fetch |
| **Message queues** | Celery, RabbitMQ, Kafka, Redis queues |
| **Existing observability** | Any existing OTEL setup, Datadog, Sentry, custom tracing, structlog |

### Step 1.3: Report findings

Before proceeding, output a summary:

```
## Detected Tech Stack

- **Language**: [detected]
- **Backend Framework**: [detected]
- **Frontend Framework**: [detected or "none"]
- **Agent Framework**: [detected or "none"]
- **Database**: [detected]
- **HTTP Client**: [detected]
- **Existing Observability**: [detected or "none"]
- **Scope**: [what will be instrumented based on argument]
```

Ask the user to confirm before proceeding to the next phase.

---

## Phase 2: Backend Instrumentation

Reference the appropriate template from `.claude/commands/instrument-otel-templates/` based on the detected language:
- Python → Read and follow `.claude/commands/instrument-otel-templates/backend-python.md`
- Node.js/TypeScript → Read and follow `.claude/commands/instrument-otel-templates/backend-node.md`
- Go → Adapt patterns from the Python template (OTEL Go SDK follows similar concepts)

### Step 2.1: Install OTEL SDK packages

Add the appropriate OTEL packages to the project's dependency file. Do NOT install — just add to the manifest so the user can install when ready.

### Step 2.2: Create telemetry initialization module

Create a telemetry initialization file (e.g., `src/telemetry.py` or `src/lib/telemetry.ts`). This file must:

1. **Configure TracerProvider** with:
   - `BatchSpanProcessor` (not `SimpleSpanProcessor` — batch is required for production)
   - `OTLPSpanExporter` (configurable endpoint via `OTEL_EXPORTER_OTLP_ENDPOINT` env var)
   - Resource attributes: `service.name`, `service.version`, `deployment.environment`
   - W3C TraceContext propagator for distributed tracing

2. **Provide helper functions**:
   - `get_tracer(name)` — returns a named tracer instance
   - `instrument_app(app)` — attaches auto-instrumentation to the web framework
   - Convenience decorator/wrapper for creating custom spans

3. **Support environment variables** (following OTEL conventions):
   - `OTEL_SERVICE_NAME` — defaults to project name
   - `OTEL_EXPORTER_OTLP_ENDPOINT` — defaults to `http://localhost:4317`
   - `OTEL_TRACES_SAMPLER` — defaults to `parentbased_always_on`
   - `OTEL_ENABLED` — kill switch, defaults to `true`

### Step 2.3: Add auto-instrumentation

Based on detected framework and libraries, add auto-instrumentation:

- **Web framework**: FastAPI → `opentelemetry-instrumentation-fastapi`, Express → `@opentelemetry/instrumentation-http` + `@opentelemetry/instrumentation-express`
- **HTTP client**: httpx → `opentelemetry-instrumentation-httpx`, axios → `@opentelemetry/instrumentation-http`
- **Database**: SQLAlchemy → `opentelemetry-instrumentation-sqlalchemy`, Prisma → manual span wrapping
- **Other**: Redis, Celery, gRPC — add matching instrumentation packages

### Step 2.4: Integrate into application startup

Modify the application entry point to initialize telemetry:
- Import and call the initialization function **before** any other imports that need instrumentation
- For Python: Add to the top of `main.py` or `app.py`
- For Node.js: Use `--require` flag or import at top of entry file

### Step 2.5: Add custom spans for business logic

Identify the 3-5 most important business operations in the codebase and add custom spans:
- Search/query operations
- External API calls not covered by auto-instrumentation
- Data processing pipelines
- Authentication flows
- Payment/transaction flows

For each, add:
- A span with a descriptive name following OTEL naming conventions (e.g., `product.search`, `seller.contact`)
- Relevant attributes (query parameters, result counts, etc.)
- Error recording on exceptions using `span.record_exception()` and `span.set_status(StatusCode.ERROR)`

### Step 2.6: Add request context propagation

Ensure trace context flows through the entire request lifecycle:
- Extract `traceparent` header from incoming requests (auto-instrumented frameworks do this)
- Inject `traceparent` into outgoing HTTP calls (auto-instrumented clients do this)
- For manual HTTP calls, explicitly propagate context

---

## Phase 3: Frontend Instrumentation

Reference `.claude/commands/instrument-otel-templates/frontend-react.md` for React/Next.js patterns.

### Step 3.1: Install browser OTEL SDK

Add to `package.json`:
- `@opentelemetry/api`
- `@opentelemetry/sdk-trace-web`
- `@opentelemetry/sdk-trace-base`
- `@opentelemetry/exporter-trace-otlp-http`
- `@opentelemetry/instrumentation-fetch`
- `@opentelemetry/instrumentation-document-load`
- `@opentelemetry/instrumentation-user-interaction`
- `@opentelemetry/context-zone`
- `@opentelemetry/resources`
- `@opentelemetry/semantic-conventions`

### Step 3.2: Create browser telemetry initialization

Create `src/lib/telemetry.ts` (or appropriate location):

1. **WebTracerProvider** with:
   - `BatchSpanProcessor` with `OTLPTraceExporter` (HTTP to collector)
   - `ZoneContextManager` for async context propagation in the browser
   - Resource: `service.name` set to frontend app name

2. **Auto-instrumentations**:
   - `FetchInstrumentation` — automatically adds `traceparent` to all `fetch()` calls to your API
   - `DocumentLoadInstrumentation` — tracks page load performance
   - `UserInteractionInstrumentation` — tracks clicks, submits

3. **Export helper functions**:
   - `initTelemetry()` — call once at app startup
   - `getTracer(name)` — get a named tracer
   - `withSpan(name, fn)` — wrap an async operation in a span

### Step 3.3: Create `useTracing()` React hook

Create a custom hook that provides tracing utilities to components:

```typescript
function useTracing(componentName: string) {
  const tracer = getTracer(componentName);

  return {
    // Wrap a user action in a span
    traceAction: (actionName: string, attributes?: Record<string, string>) => {
      return <T>(fn: () => Promise<T>): Promise<T> => {
        return tracer.startActiveSpan(`${componentName}.${actionName}`, async (span) => {
          try {
            if (attributes) Object.entries(attributes).forEach(([k, v]) => span.setAttribute(k, v));
            const result = await fn();
            span.setStatus({ code: SpanStatusCode.OK });
            return result;
          } catch (error) {
            span.recordException(error);
            span.setStatus({ code: SpanStatusCode.ERROR });
            throw error;
          } finally {
            span.end();
          }
        });
      };
    },

    // Record a user event (non-async)
    traceEvent: (eventName: string, attributes?: Record<string, string>) => {
      const span = tracer.startSpan(`${componentName}.${eventName}`);
      if (attributes) Object.entries(attributes).forEach(([k, v]) => span.setAttribute(k, v));
      span.end();
    }
  };
}
```

### Step 3.4: Add session tracking

Generate or retrieve a session ID and attach it to all spans:
- Use `crypto.randomUUID()` or a session store
- Set `session.id` as a span attribute on all frontend spans
- Pass `session.id` as a custom header (e.g., `X-Session-Id`) in API calls
- Backend should extract and attach to its spans too

### Step 3.5: Initialize in app entry point

Add telemetry initialization to the app's root:
- For Next.js App Router: Add to `layout.tsx` via a client component wrapper
- For Next.js Pages Router: Add to `_app.tsx`
- For Vite/CRA: Add to `main.tsx`

**Important**: Telemetry init must run client-side only. Use `useEffect` or dynamic import for SSR frameworks.

### Step 3.6: Add error boundary integration

Create or modify the error boundary to record exceptions as span events:
- Catch errors in React Error Boundary
- Create a span with the error details
- Record the component stack trace as a span attribute

---

## Phase 4: Agentic Flow Instrumentation

This is the most valuable phase for AI-powered applications. Reference `.claude/commands/instrument-otel-templates/agentic-flows.md`.

### Step 4.1: Identify the agent framework

Based on Phase 1 detection, determine the agent architecture:
- **OpenAI Agents SDK** (`openai-agents` / `agents`): Uses hooks lifecycle
- **LangChain**: Uses callbacks
- **CrewAI**: Uses callbacks/hooks
- **Custom agent loop**: Direct instrumentation needed

### Step 4.2: Create OTEL hooks/callbacks class

Create an instrumentation class that hooks into the agent framework's lifecycle. The class must handle:

**Span hierarchy:**
```
[HTTP Request Span]
  └── [Agent Run: "search_agent"]
        ├── [LLM Call: "gpt-4o"]
        │     ├── attribute: gen_ai.request.model = "gpt-4o"
        │     ├── attribute: gen_ai.usage.input_tokens = 150
        │     └── attribute: gen_ai.usage.output_tokens = 89
        ├── [Tool Call: "web_search"]
        │     ├── attribute: tool.name = "web_search"
        │     ├── attribute: tool.input = "best price for..."
        │     └── attribute: tool.cached = false
        ├── [LLM Call: "gpt-4o"]  (second call after tool result)
        └── [Agent Handoff: → "pricing_agent"]
              └── [Agent Run: "pricing_agent"]
                    ├── [LLM Call: "gpt-4o-mini"]
                    └── [Tool Call: "calculate_price"]
```

**Context management:**
- Use OTEL context propagation (`context.attach()` / `context.detach()`) to maintain parent-child relationships
- Each agent run creates a new span and sets it as the active context
- Child operations (LLM calls, tool calls) automatically become children of the active agent span
- On handoff, create a link between the source and target agent spans

**Semantic attributes** (following OTEL Gen AI conventions):
- `gen_ai.system` — "openai", "anthropic", etc.
- `gen_ai.request.model` — model name requested
- `gen_ai.response.model` — model name in response
- `gen_ai.usage.input_tokens` — prompt token count
- `gen_ai.usage.output_tokens` — completion token count
- `gen_ai.usage.total_tokens` — total tokens
- `agent.name` — name of the agent
- `agent.type` — type/role of the agent
- `tool.name` — name of the tool being called
- `tool.input` — tool input (truncated if large)
- `tool.output` — tool output (truncated if large)
- `tool.cached` — whether the result was cached

### Step 4.3: Handle parallel tool calls

When the agent framework executes multiple tools in parallel:
- Each tool call gets its own span, all sharing the same parent (the LLM call or agent run)
- OTEL handles this natively — just create spans in the same context
- Do NOT serialize parallel operations into sequential spans

### Step 4.4: Add session-level correlation

For multi-turn conversations:
- Accept a `session_id` parameter in the agent hooks
- Set `session.id` as a span attribute on the root agent span
- All child spans inherit the trace ID, giving natural correlation
- For separate requests in the same session, use `session.id` attribute for cross-trace grouping

### Step 4.5: Register the hooks with the agent framework

Modify the agent initialization code to register the OTEL hooks:
- For OpenAI Agents SDK: Pass hooks to `Runner.run()` or set as default
- For LangChain: Add as callback handler
- For custom: Wrap the agent loop with span creation

---

## Phase 5: Collector & Visualization Setup

Reference `.claude/commands/instrument-otel-templates/collector-configs.md`.

### Step 5.1: Generate OTEL Collector config

Create `otel-collector-config.yaml` in the project root:

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
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger, debug]
```

### Step 5.2: Generate Docker Compose file

Create `docker-compose.otel.yaml`:

```yaml
version: "3.8"

services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
    depends_on:
      - jaeger

  jaeger:
    image: jaegertracing/jaeger:latest
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686" # Jaeger UI
      - "4317"        # OTLP gRPC (internal, used by collector)
```

### Step 5.3: Generate environment variables template

Create `.env.otel.example`:

```bash
# OpenTelemetry Configuration
OTEL_ENABLED=true
OTEL_SERVICE_NAME=my-service
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_TRACES_SAMPLER=parentbased_always_on

# Collector Configuration
OTEL_COLLECTOR_ENDPOINT=http://localhost:4317

# Frontend OTEL (browser sends to collector via HTTP)
NEXT_PUBLIC_OTEL_ENDPOINT=http://localhost:4318/v1/traces
NEXT_PUBLIC_OTEL_SERVICE_NAME=my-frontend
```

### Step 5.4: Add .gitignore entries

Add to `.gitignore` if not already present:
```
# OTEL local data
.env.otel
```

### Step 5.5: Create a startup script

Create a helper script `otel-up.sh`:
```bash
#!/bin/bash
# Start OTEL Collector + Jaeger for local development
docker-compose -f docker-compose.otel.yaml up -d
echo "OTEL Collector running on :4317 (gRPC) and :4318 (HTTP)"
echo "Jaeger UI: http://localhost:16686"
```

---

## Post-Instrumentation Checklist

After completing all applicable phases, output this checklist:

```
## Instrumentation Complete!

### What was added:
- [ ] Telemetry initialization module
- [ ] Auto-instrumentation for [framework]
- [ ] Custom spans for business operations
- [ ] Frontend browser tracing (if applicable)
- [ ] Agent/LLM flow tracing (if applicable)
- [ ] OTEL Collector config
- [ ] Docker Compose for local visualization
- [ ] Environment variables template

### Next steps:
1. Install new dependencies: [exact command]
2. Copy `.env.otel.example` to `.env.otel` and configure
3. Start the collector: `./otel-up.sh` or `docker-compose -f docker-compose.otel.yaml up -d`
4. Start your application
5. Open Jaeger UI: http://localhost:16686
6. Trigger some operations and verify traces appear

### Verify these work:
- [ ] API request traces show in Jaeger
- [ ] Frontend → Backend traces are linked (same trace ID)
- [ ] Agent flows show nested spans (agent → LLM → tool)
- [ ] Errors are recorded with stack traces
- [ ] Session ID appears as a searchable attribute
```

---

## Important Guidelines

1. **Read before writing**: Always read existing files before modifying them. Understand the current code structure.
2. **Non-destructive**: Never remove existing code. Add instrumentation alongside it.
3. **Follow existing patterns**: Match the project's code style, naming conventions, and file organization.
4. **Minimal changes**: Don't refactor existing code. Only add what's needed for instrumentation.
5. **Test compatibility**: Ensure added code doesn't break existing tests. Run tests after changes.
6. **Commit separately**: Each phase should be its own commit with a descriptive message.
7. **Use templates**: Reference the template files in `.claude/commands/instrument-otel-templates/` for code patterns — don't invent from scratch.
