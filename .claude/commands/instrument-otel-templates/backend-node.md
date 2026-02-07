# Backend Node.js OTEL Instrumentation Template

Reference patterns for instrumenting Node.js/TypeScript backends with OpenTelemetry.

---

## Dependencies

Add to `package.json`:

```json
{
  "dependencies": {
    "@opentelemetry/api": "^1.9.0",
    "@opentelemetry/sdk-node": "^0.56.0",
    "@opentelemetry/sdk-trace-node": "^1.27.0",
    "@opentelemetry/sdk-trace-base": "^1.27.0",
    "@opentelemetry/exporter-trace-otlp-grpc": "^0.56.0",
    "@opentelemetry/resources": "^1.27.0",
    "@opentelemetry/semantic-conventions": "^1.27.0",
    "@opentelemetry/instrumentation-http": "^0.56.0",
    "@opentelemetry/instrumentation-express": "^0.44.0",
    "@opentelemetry/instrumentation-fastify": "^0.42.0",
    "@opentelemetry/instrumentation-koa": "^0.43.0",
    "@opentelemetry/instrumentation-pg": "^0.48.0",
    "@opentelemetry/instrumentation-mysql": "^0.42.0",
    "@opentelemetry/instrumentation-redis-4": "^0.43.0",
    "@opentelemetry/instrumentation-ioredis": "^0.43.0",
    "@opentelemetry/instrumentation-grpc": "^0.56.0"
  }
}
```

Only include the instrumentation packages relevant to the detected stack.

---

## Telemetry Initialization Module

Create `src/telemetry.ts` (or `src/lib/telemetry.ts`):

```typescript
/**
 * OpenTelemetry initialization and utilities.
 *
 * IMPORTANT: Import this file BEFORE any other application code.
 * Auto-instrumentation must patch modules before they are loaded.
 *
 * Usage:
 *   // At the very top of your entry file (e.g., server.ts):
 *   import { initTelemetry } from './telemetry';
 *   initTelemetry({ serviceName: 'my-api' });
 *
 *   // Then import everything else
 *   import express from 'express';
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-grpc';
import { Resource } from '@opentelemetry/resources';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
  ATTR_DEPLOYMENT_ENVIRONMENT,
} from '@opentelemetry/semantic-conventions';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import {
  trace,
  context,
  SpanStatusCode,
  type Tracer,
  type Span,
} from '@opentelemetry/api';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';

// Add framework-specific imports based on detected stack:
// import { ExpressInstrumentation } from '@opentelemetry/instrumentation-express';
// import { FastifyInstrumentation } from '@opentelemetry/instrumentation-fastify';
// import { PgInstrumentation } from '@opentelemetry/instrumentation-pg';

let sdk: NodeSDK | null = null;

interface TelemetryConfig {
  serviceName?: string;
  serviceVersion?: string;
  environment?: string;
  endpoint?: string;
  enabled?: boolean;
}

export function initTelemetry(config: TelemetryConfig = {}): void {
  const {
    serviceName = process.env.OTEL_SERVICE_NAME || 'unknown-service',
    serviceVersion = process.env.OTEL_SERVICE_VERSION || '0.1.0',
    environment = process.env.DEPLOYMENT_ENVIRONMENT || 'development',
    endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4317',
    enabled = process.env.OTEL_ENABLED !== 'false',
  } = config;

  if (!enabled) {
    console.log('OpenTelemetry disabled via OTEL_ENABLED=false');
    return;
  }

  const resource = new Resource({
    [ATTR_SERVICE_NAME]: serviceName,
    [ATTR_SERVICE_VERSION]: serviceVersion,
    [ATTR_DEPLOYMENT_ENVIRONMENT]: environment,
  });

  const traceExporter = new OTLPTraceExporter({ url: endpoint });

  sdk = new NodeSDK({
    resource,
    spanProcessors: [new BatchSpanProcessor(traceExporter)],
    instrumentations: [
      new HttpInstrumentation({
        ignoreIncomingPaths: ['/health', '/healthz', '/ready', '/readyz'],
      }),
      // Add framework-specific instrumentations:
      // new ExpressInstrumentation(),
      // new FastifyInstrumentation(),
      // new PgInstrumentation(),
    ],
  });

  sdk.start();
  console.log(`OpenTelemetry initialized: service=${serviceName}, endpoint=${endpoint}`);

  // Graceful shutdown
  const shutdown = async () => {
    try {
      await sdk?.shutdown();
      console.log('OpenTelemetry shut down successfully');
    } catch (err) {
      console.error('Error shutting down OpenTelemetry:', err);
    }
  };

  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

/**
 * Get a named tracer instance.
 */
export function getTracer(name: string): Tracer {
  return trace.getTracer(name);
}

/**
 * Wrap an async function in a span.
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
 * Decorator for class methods — wraps in a span.
 * Usage: @Traced('operation.name')
 */
export function Traced(spanName?: string) {
  return function (
    target: any,
    propertyKey: string,
    descriptor: PropertyDescriptor,
  ) {
    const originalMethod = descriptor.value;
    const name = spanName || `${target.constructor.name}.${propertyKey}`;
    const tracer = getTracer(target.constructor.name);

    descriptor.value = async function (...args: any[]) {
      return tracer.startActiveSpan(name, async (span: Span) => {
        try {
          const result = await originalMethod.apply(this, args);
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
    };

    return descriptor;
  };
}
```

---

## Express Integration

```typescript
// server.ts — OTEL must be initialized FIRST
import { initTelemetry } from './telemetry';
initTelemetry({ serviceName: 'my-express-api' });

// Now import Express and other modules
import express from 'express';

const app = express();

// Session ID middleware
app.use((req, res, next) => {
  const span = trace.getActiveSpan();
  const sessionId = req.headers['x-session-id'];
  if (span && sessionId) {
    span.setAttribute('session.id', sessionId as string);
  }
  next();
});

// Error handling middleware
app.use((err: Error, req: express.Request, res: express.Response, next: express.NextFunction) => {
  const span = trace.getActiveSpan();
  if (span) {
    span.recordException(err);
    span.setStatus({ code: SpanStatusCode.ERROR, message: err.message });
  }
  res.status(500).json({ error: 'Internal Server Error' });
});
```

---

## Fastify Integration

```typescript
import { initTelemetry } from './telemetry';
initTelemetry({ serviceName: 'my-fastify-api' });

import Fastify from 'fastify';

const app = Fastify();

// Session ID hook
app.addHook('onRequest', async (request, reply) => {
  const span = trace.getActiveSpan();
  const sessionId = request.headers['x-session-id'];
  if (span && sessionId) {
    span.setAttribute('session.id', sessionId as string);
  }
});
```

---

## Next.js API Routes Integration

For Next.js API routes (Pages Router or App Router route handlers):

```typescript
// src/lib/api-tracing.ts
import { getTracer, withSpan } from './telemetry';

/**
 * Wrap a Next.js API route handler with tracing.
 */
export function withTracing(
  handler: (req: Request) => Promise<Response>,
  routeName: string,
) {
  return async (req: Request): Promise<Response> => {
    return withSpan('next-api', routeName, async (span) => {
      span.setAttribute('http.method', req.method);
      span.setAttribute('http.url', req.url);

      const sessionId = req.headers.get('x-session-id');
      if (sessionId) {
        span.setAttribute('session.id', sessionId);
      }

      const response = await handler(req);
      span.setAttribute('http.status_code', response.status);
      return response;
    });
  };
}

// Usage in route handler:
// export const GET = withTracing(async (req) => { ... }, 'api.users.list');
```

---

## Custom Span Examples

### Search operation

```typescript
import { getTracer } from './telemetry';

const tracer = getTracer('search-service');

async function searchProducts(query: string, filters: Record<string, string>) {
  return tracer.startActiveSpan('product.search', async (span) => {
    span.setAttribute('search.query', query);
    span.setAttribute('search.filters', JSON.stringify(filters));

    try {
      const results = await doSearch(query, filters);
      span.setAttribute('search.result_count', results.length);
      span.setStatus({ code: SpanStatusCode.OK });
      return results;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
```

### Database query

```typescript
async function getUserById(userId: string) {
  return tracer.startActiveSpan('db.get_user', async (span) => {
    span.setAttribute('db.system', 'postgresql');
    span.setAttribute('db.operation', 'SELECT');
    span.setAttribute('user.id', userId);

    const user = await prisma.user.findUnique({ where: { id: userId } });

    span.setAttribute('db.result', user ? 'found' : 'not_found');
    span.end();
    return user;
  });
}
```

---

## Prisma Instrumentation (Manual)

Prisma doesn't have official OTEL auto-instrumentation. Use middleware:

```typescript
import { getTracer } from './telemetry';
import { PrismaClient } from '@prisma/client';

const tracer = getTracer('prisma');
const prisma = new PrismaClient();

prisma.$use(async (params, next) => {
  return tracer.startActiveSpan(
    `prisma.${params.model}.${params.action}`,
    async (span) => {
      span.setAttribute('db.system', 'prisma');
      span.setAttribute('db.operation', params.action);
      if (params.model) span.setAttribute('db.collection.name', params.model);

      try {
        const result = await next(params);
        span.setStatus({ code: SpanStatusCode.OK });
        return result;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    },
  );
});
```

---

## TypeORM Instrumentation

```typescript
// TypeORM has no official OTEL package — use subscriber pattern:
import { EntitySubscriberInterface, EventSubscriber, InsertEvent, UpdateEvent } from 'typeorm';
import { getTracer } from './telemetry';

const tracer = getTracer('typeorm');

@EventSubscriber()
export class OtelSubscriber implements EntitySubscriberInterface {
  beforeInsert(event: InsertEvent<any>) {
    const span = tracer.startSpan(`typeorm.insert.${event.metadata.tableName}`);
    span.setAttribute('db.system', 'typeorm');
    span.setAttribute('db.operation', 'INSERT');
    span.setAttribute('db.collection.name', event.metadata.tableName);
    // Store span on entity for afterInsert
    (event.entity as any).__otelSpan = span;
  }

  afterInsert(event: InsertEvent<any>) {
    const span = (event.entity as any).__otelSpan;
    if (span) {
      span.setStatus({ code: SpanStatusCode.OK });
      span.end();
      delete (event.entity as any).__otelSpan;
    }
  }
}
```

---

## Graceful Shutdown

The `NodeSDK` handles shutdown via the signal handlers registered in `initTelemetry()`. For custom shutdown logic:

```typescript
import { trace } from '@opentelemetry/api';

async function shutdownTelemetry(): Promise<void> {
  const provider = trace.getTracerProvider();
  if ('shutdown' in provider) {
    await (provider as any).shutdown();
  }
}
```
