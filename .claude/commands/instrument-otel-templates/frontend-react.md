# Frontend React/Next.js OTEL Instrumentation Template

Reference patterns for instrumenting React and Next.js frontends with OpenTelemetry in the browser.

---

## Dependencies

Add to the frontend `package.json`:

```json
{
  "dependencies": {
    "@opentelemetry/api": "^1.9.0",
    "@opentelemetry/sdk-trace-web": "^1.27.0",
    "@opentelemetry/sdk-trace-base": "^1.27.0",
    "@opentelemetry/exporter-trace-otlp-http": "^0.56.0",
    "@opentelemetry/instrumentation-fetch": "^0.56.0",
    "@opentelemetry/instrumentation-document-load": "^0.41.0",
    "@opentelemetry/instrumentation-user-interaction": "^0.41.0",
    "@opentelemetry/context-zone": "^1.27.0",
    "@opentelemetry/resources": "^1.27.0",
    "@opentelemetry/semantic-conventions": "^1.27.0",
    "@opentelemetry/instrumentation": "^0.56.0"
  }
}
```

---

## Browser Telemetry Initialization

Create `src/lib/telemetry.ts`:

```typescript
/**
 * Browser-side OpenTelemetry initialization.
 *
 * Call `initTelemetry()` once at app startup (client-side only).
 * In Next.js, use a client component or useEffect to ensure
 * this only runs in the browser.
 */

import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { ZoneContextManager } from '@opentelemetry/context-zone';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load';
import { UserInteractionInstrumentation } from '@opentelemetry/instrumentation-user-interaction';
import {
  trace,
  SpanStatusCode,
  type Tracer,
  type Span,
  context,
} from '@opentelemetry/api';

let initialized = false;
let sessionId: string | null = null;

/**
 * Generate or retrieve a session ID for cross-request correlation.
 */
function getSessionId(): string {
  if (sessionId) return sessionId;

  // Check sessionStorage first
  const stored = sessionStorage.getItem('otel_session_id');
  if (stored) {
    sessionId = stored;
    return stored;
  }

  // Generate new session ID
  sessionId = crypto.randomUUID();
  sessionStorage.setItem('otel_session_id', sessionId);
  return sessionId;
}

interface TelemetryConfig {
  serviceName?: string;
  endpoint?: string;
  apiBaseUrl?: string;
}

export function initTelemetry(config: TelemetryConfig = {}): void {
  if (initialized) return;
  if (typeof window === 'undefined') return; // SSR guard

  const {
    serviceName = process.env.NEXT_PUBLIC_OTEL_SERVICE_NAME || 'frontend',
    endpoint = process.env.NEXT_PUBLIC_OTEL_ENDPOINT || 'http://localhost:4318/v1/traces',
    apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  } = config;

  const resource = new Resource({
    [ATTR_SERVICE_NAME]: serviceName,
  });

  const provider = new WebTracerProvider({
    resource,
  });

  const exporter = new OTLPTraceExporter({
    url: endpoint,
  });

  provider.addSpanProcessor(new BatchSpanProcessor(exporter));

  // Use Zone.js for async context propagation in the browser
  provider.register({
    contextManager: new ZoneContextManager(),
  });

  // Register auto-instrumentations
  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        // Propagate trace context to your API
        propagateTraceHeaderCorsUrls: [
          new RegExp(apiBaseUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
        ],
        // Add session ID to all outgoing requests
        applyCustomAttributesOnSpan: (span: Span) => {
          span.setAttribute('session.id', getSessionId());
        },
        // Optionally clear timing to avoid CORS issues
        clearTimingResources: true,
      }),
      new DocumentLoadInstrumentation(),
      new UserInteractionInstrumentation({
        eventNames: ['click', 'submit'],
      }),
    ],
  });

  initialized = true;
  console.log(`[OTEL] Browser telemetry initialized: service=${serviceName}`);
}

/**
 * Get a named tracer instance.
 */
export function getTracer(name: string): Tracer {
  return trace.getTracer(name);
}

/**
 * Wrap an async operation in a traced span.
 */
export async function withSpan<T>(
  tracerName: string,
  spanName: string,
  fn: (span: Span) => Promise<T>,
  attributes?: Record<string, string | number | boolean>,
): Promise<T> {
  const tracer = getTracer(tracerName);
  return tracer.startActiveSpan(spanName, async (span) => {
    try {
      span.setAttribute('session.id', getSessionId());
      if (attributes) {
        Object.entries(attributes).forEach(([k, v]) => span.setAttribute(k, v));
      }
      const result = await fn(span);
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: (error as Error).message,
      });
      throw error;
    } finally {
      span.end();
    }
  });
}

/**
 * Get the current session ID (for passing as custom header).
 */
export { getSessionId };
```

---

## useTracing React Hook

Create `src/hooks/useTracing.ts` (or add to existing hooks directory):

```typescript
'use client';

import { useCallback, useRef } from 'react';
import { getTracer, getSessionId } from '@/lib/telemetry';
import { SpanStatusCode, type Span } from '@opentelemetry/api';

/**
 * React hook providing tracing utilities for components.
 *
 * Usage:
 *   const { traceAction, traceEvent } = useTracing('SearchPage');
 *
 *   // Wrap an async action
 *   const handleSearch = traceAction('search', { query })(async () => {
 *     const results = await api.search(query);
 *     return results;
 *   });
 *
 *   // Record a one-off event
 *   traceEvent('button_click', { button: 'submit' });
 */
export function useTracing(componentName: string) {
  const tracerRef = useRef(getTracer(componentName));

  /**
   * Wrap an async action in a span.
   * Returns a function that executes the action within the span.
   */
  const traceAction = useCallback(
    (actionName: string, attributes?: Record<string, string | number | boolean>) => {
      return <T>(fn: () => Promise<T>): Promise<T> => {
        return tracerRef.current.startActiveSpan(
          `${componentName}.${actionName}`,
          async (span: Span) => {
            try {
              span.setAttribute('session.id', getSessionId());
              span.setAttribute('component', componentName);
              span.setAttribute('action', actionName);
              if (attributes) {
                Object.entries(attributes).forEach(([k, v]) =>
                  span.setAttribute(k, v),
                );
              }
              const result = await fn();
              span.setStatus({ code: SpanStatusCode.OK });
              return result;
            } catch (error) {
              span.recordException(error as Error);
              span.setStatus({
                code: SpanStatusCode.ERROR,
                message: (error as Error).message,
              });
              throw error;
            } finally {
              span.end();
            }
          },
        );
      };
    },
    [componentName],
  );

  /**
   * Record a fire-and-forget event (non-async).
   */
  const traceEvent = useCallback(
    (eventName: string, attributes?: Record<string, string | number | boolean>) => {
      const span = tracerRef.current.startSpan(`${componentName}.${eventName}`);
      span.setAttribute('session.id', getSessionId());
      span.setAttribute('component', componentName);
      span.setAttribute('event', eventName);
      if (attributes) {
        Object.entries(attributes).forEach(([k, v]) => span.setAttribute(k, v));
      }
      span.end();
    },
    [componentName],
  );

  return { traceAction, traceEvent };
}
```

---

## Next.js App Router Integration

### Telemetry Provider Component

Create `src/components/TelemetryProvider.tsx`:

```tsx
'use client';

import { useEffect } from 'react';
import { initTelemetry } from '@/lib/telemetry';

/**
 * Client component that initializes browser telemetry.
 * Add to your root layout.
 */
export function TelemetryProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    initTelemetry();
  }, []);

  return <>{children}</>;
}
```

### Add to Root Layout

In `app/layout.tsx`:

```tsx
import { TelemetryProvider } from '@/components/TelemetryProvider';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <TelemetryProvider>
          {children}
        </TelemetryProvider>
      </body>
    </html>
  );
}
```

---

## Next.js Pages Router Integration

In `pages/_app.tsx`:

```tsx
import { useEffect } from 'react';
import { initTelemetry } from '@/lib/telemetry';
import type { AppProps } from 'next/app';

export default function App({ Component, pageProps }: AppProps) {
  useEffect(() => {
    initTelemetry();
  }, []);

  return <Component {...pageProps} />;
}
```

---

## Vite / CRA Integration

In `src/main.tsx`:

```tsx
import { initTelemetry } from './lib/telemetry';

// Initialize telemetry before rendering
initTelemetry();

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

---

## Error Boundary with Tracing

Create `src/components/TracedErrorBoundary.tsx`:

```tsx
'use client';

import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { getTracer } from '@/lib/telemetry';
import { SpanStatusCode } from '@opentelemetry/api';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class TracedErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    const tracer = getTracer('error-boundary');
    const span = tracer.startSpan('react.error_boundary');

    span.recordException(error);
    span.setAttribute('error.type', error.name);
    span.setAttribute('error.message', error.message);
    if (errorInfo.componentStack) {
      span.setAttribute('error.component_stack', errorInfo.componentStack);
    }
    span.setStatus({
      code: SpanStatusCode.ERROR,
      message: error.message,
    });
    span.end();
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div style={{ padding: '20px', textAlign: 'center' }}>
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
        </div>
      );
    }

    return this.props.children;
  }
}
```

---

## API Client Integration

If the project has a centralized API client, add session ID header:

```typescript
// src/lib/api.ts — example modification
import { getSessionId } from './telemetry';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchAPI(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);

  // Add session ID for cross-trace correlation
  headers.set('X-Session-Id', getSessionId());

  return fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });
}
```

Note: The `FetchInstrumentation` automatically adds `traceparent` headers, so distributed tracing works without manual header injection. The `X-Session-Id` header is for session-level (multi-request) correlation.

---

## Route Change Tracking (Next.js App Router)

Create `src/components/RouteTracker.tsx`:

```tsx
'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { getTracer, getSessionId } from '@/lib/telemetry';
import { SpanStatusCode } from '@opentelemetry/api';

export function RouteTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const prevPathRef = useRef<string>('');

  useEffect(() => {
    if (pathname === prevPathRef.current) return;

    const tracer = getTracer('navigation');
    const span = tracer.startSpan('route.change');
    span.setAttribute('session.id', getSessionId());
    span.setAttribute('route.path', pathname);
    span.setAttribute('route.previous', prevPathRef.current);
    if (searchParams.toString()) {
      span.setAttribute('route.search_params', searchParams.toString());
    }
    span.setStatus({ code: SpanStatusCode.OK });
    span.end();

    prevPathRef.current = pathname;
  }, [pathname, searchParams]);

  return null;
}
```

Add `<RouteTracker />` inside the `TelemetryProvider`.

---

## Usage Examples

### Search component

```tsx
'use client';

import { useTracing } from '@/hooks/useTracing';

export function SearchBar() {
  const { traceAction, traceEvent } = useTracing('SearchBar');
  const [query, setQuery] = useState('');

  const handleSearch = async () => {
    traceEvent('search_initiated', { query });

    await traceAction('search', { query })(async () => {
      const results = await api.search(query);
      setResults(results);
    });
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); handleSearch(); }}>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <button type="submit">Search</button>
    </form>
  );
}
```

### Form submission

```tsx
const { traceAction } = useTracing('ContactForm');

const handleSubmit = async (data: FormData) => {
  await traceAction('submit', {
    'form.fields': Object.keys(data).join(','),
  })(async () => {
    await api.submitContact(data);
  });
};
```

---

## CORS Configuration

The OTEL collector must accept requests from the browser. The collector config should include:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins: ["*"]  # Restrict in production
          allowed_headers: ["*"]
```

Also ensure your API server allows the `traceparent` header in CORS:

```python
# FastAPI example
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_headers=["*"],  # Must include traceparent
)
```
