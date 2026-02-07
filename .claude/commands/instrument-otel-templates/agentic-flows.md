# Agentic Flow OTEL Instrumentation Template

Reference patterns for instrumenting AI agent frameworks with OpenTelemetry. Covers OpenAI Agents SDK, LangChain, and custom agent loops.

---

## Semantic Conventions for Gen AI

These attributes follow the [OpenTelemetry Semantic Conventions for Gen AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/):

| Attribute | Description | Example |
|---|---|---|
| `gen_ai.system` | AI provider | `"openai"`, `"anthropic"` |
| `gen_ai.request.model` | Model requested | `"gpt-4o"` |
| `gen_ai.response.model` | Model in response | `"gpt-4o-2024-08-06"` |
| `gen_ai.usage.input_tokens` | Prompt tokens | `150` |
| `gen_ai.usage.output_tokens` | Completion tokens | `89` |
| `gen_ai.usage.total_tokens` | Total tokens | `239` |
| `agent.name` | Agent name | `"search_agent"` |
| `agent.type` | Agent role/type | `"researcher"` |
| `tool.name` | Tool being called | `"web_search"` |
| `tool.input` | Tool input (truncated) | `"search for..."` |
| `tool.output` | Tool output (truncated) | `"Found 5 results"` |
| `tool.cached` | Cache hit | `true` / `false` |
| `session.id` | Session identifier | `"abc-123"` |

---

## OpenAI Agents SDK (Python)

The OpenAI Agents SDK uses a hooks-based lifecycle. Create an OTEL hooks class.

### OTEL Hooks Implementation

Create `src/observability/agent_hooks.py`:

```python
"""
OpenTelemetry hooks for OpenAI Agents SDK.

Provides distributed tracing for agent runs, LLM calls, tool calls,
and agent handoffs.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from opentelemetry import trace, context
from opentelemetry.trace import StatusCode, Status, Span, SpanKind
from agents import (
    AgentHooks,
    RunHooks,
    RunContextWrapper,
    Tool,
    Agent,
)
from agents.result import RunResult
from agents.models.interface import ModelResponse

from src.telemetry import get_tracer

# Max length for attribute values to avoid oversized spans
_MAX_ATTR_LENGTH = 1024


def _truncate(value: Any, max_length: int = _MAX_ATTR_LENGTH) -> str:
    """Truncate a value to max_length for span attributes."""
    s = str(value)
    if len(s) > max_length:
        return s[:max_length] + "...[truncated]"
    return s


class OTELRunHooks(RunHooks):
    """
    Hooks that trace the entire agent run lifecycle.

    Usage:
        from src.observability.agent_hooks import OTELRunHooks

        result = await Runner.run(
            agent,
            input=user_message,
            hooks=OTELRunHooks(session_id="user-session-123"),
        )
    """

    def __init__(self, session_id: Optional[str] = None):
        self.tracer = get_tracer("agents")
        self.session_id = session_id
        self._agent_spans: dict[str, Span] = {}
        self._agent_tokens: dict[str, object] = {}

    async def on_agent_start(
        self, context: RunContextWrapper, agent: Agent
    ) -> None:
        """Create a span when an agent starts running."""
        span = self.tracer.start_span(
            f"agent.run:{agent.name}",
            kind=SpanKind.INTERNAL,
            attributes={
                "agent.name": agent.name,
                "agent.type": getattr(agent, "type", "default"),
                "gen_ai.system": "openai",
            },
        )

        if self.session_id:
            span.set_attribute("session.id", self.session_id)

        if agent.model:
            span.set_attribute("gen_ai.request.model", str(agent.model))

        # Set span as active context
        token = trace.context_api.attach(
            trace.set_span_in_context(span)
        )
        self._agent_spans[agent.name] = span
        self._agent_tokens[agent.name] = token

    async def on_agent_end(
        self, context: RunContextWrapper, agent: Agent, output: Any
    ) -> None:
        """End the agent span when the agent completes."""
        span = self._agent_spans.pop(agent.name, None)
        token = self._agent_tokens.pop(agent.name, None)

        if span:
            span.set_attribute("agent.output", _truncate(output))
            span.set_status(Status(StatusCode.OK))
            span.end()

        if token:
            trace.context_api.detach(token)

    async def on_llm_start(
        self, context: RunContextWrapper, agent: Agent, model_settings: Any
    ) -> None:
        """Create a child span for an LLM call."""
        parent_span = self._agent_spans.get(agent.name)
        ctx = trace.set_span_in_context(parent_span) if parent_span else None

        span = self.tracer.start_span(
            f"llm.call:{agent.name}",
            kind=SpanKind.CLIENT,
            context=ctx,
            attributes={
                "gen_ai.system": "openai",
                "gen_ai.request.model": str(
                    getattr(model_settings, "model", agent.model or "unknown")
                ),
            },
        )

        # Store LLM span keyed by agent name (overwritten on each call)
        self._agent_spans[f"{agent.name}:llm"] = span

    async def on_llm_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        response: ModelResponse,
    ) -> None:
        """End the LLM span and record token usage."""
        span = self._agent_spans.pop(f"{agent.name}:llm", None)
        if not span:
            return

        if hasattr(response, "usage") and response.usage:
            usage = response.usage
            if hasattr(usage, "input_tokens"):
                span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            if hasattr(usage, "output_tokens"):
                span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            total = getattr(usage, "total_tokens", None)
            if total:
                span.set_attribute("gen_ai.usage.total_tokens", total)

        if hasattr(response, "model") and response.model:
            span.set_attribute("gen_ai.response.model", response.model)

        span.set_status(Status(StatusCode.OK))
        span.end()

    async def on_tool_start(
        self, context: RunContextWrapper, agent: Agent, tool: Tool, input: str
    ) -> None:
        """Create a child span for a tool call."""
        parent_span = self._agent_spans.get(agent.name)
        ctx = trace.set_span_in_context(parent_span) if parent_span else None

        span = self.tracer.start_span(
            f"tool.call:{tool.name}",
            kind=SpanKind.INTERNAL,
            context=ctx,
            attributes={
                "tool.name": tool.name,
                "tool.input": _truncate(input),
            },
        )

        self._agent_spans[f"{agent.name}:tool:{tool.name}"] = span

    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Tool,
        result: str,
    ) -> None:
        """End the tool span and record output."""
        span = self._agent_spans.pop(f"{agent.name}:tool:{tool.name}", None)
        if not span:
            return

        span.set_attribute("tool.output", _truncate(result))
        span.set_status(Status(StatusCode.OK))
        span.end()

    async def on_handoff(
        self,
        context: RunContextWrapper,
        from_agent: Agent,
        to_agent: Agent,
    ) -> None:
        """Record a handoff between agents as a span event."""
        span = self._agent_spans.get(from_agent.name)
        if span:
            span.add_event(
                "agent.handoff",
                attributes={
                    "handoff.from": from_agent.name,
                    "handoff.to": to_agent.name,
                },
            )
```

### Integration with Runner

```python
from agents import Runner
from src.observability.agent_hooks import OTELRunHooks

# Simple usage
result = await Runner.run(
    agent,
    input="Find the best price for iPhone 16",
    hooks=OTELRunHooks(session_id="user-123"),
)

# With existing trace context (e.g., from FastAPI request)
async def handle_request(request: Request):
    session_id = request.headers.get("x-session-id")
    # The current span from FastAPI auto-instrumentation becomes the parent
    result = await Runner.run(
        agent,
        input=request.json()["message"],
        hooks=OTELRunHooks(session_id=session_id),
    )
    return result
```

---

## LangChain (Python)

LangChain uses callbacks. Create an OTEL callback handler.

### OTEL Callback Handler

Create `src/observability/langchain_callbacks.py`:

```python
"""
OpenTelemetry callback handler for LangChain.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from opentelemetry import trace
from opentelemetry.trace import StatusCode, Status, Span, SpanKind

from src.telemetry import get_tracer

_MAX_ATTR_LENGTH = 1024


def _truncate(value: Any) -> str:
    s = str(value)
    return s[:_MAX_ATTR_LENGTH] + "...[truncated]" if len(s) > _MAX_ATTR_LENGTH else s


class OTELCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that creates OTEL spans for
    LLM calls, chain runs, and tool calls.

    Usage:
        handler = OTELCallbackHandler(session_id="user-123")
        chain.invoke(input, config={"callbacks": [handler]})
    """

    def __init__(self, session_id: Optional[str] = None):
        self.tracer = get_tracer("langchain")
        self.session_id = session_id
        self._spans: Dict[UUID, Span] = {}
        self._tokens: Dict[UUID, object] = {}

    def _start_span(
        self,
        run_id: UUID,
        name: str,
        parent_run_id: Optional[UUID] = None,
        attributes: Optional[Dict] = None,
    ) -> Span:
        parent_ctx = None
        if parent_run_id and parent_run_id in self._spans:
            parent_ctx = trace.set_span_in_context(self._spans[parent_run_id])

        span = self.tracer.start_span(
            name,
            kind=SpanKind.INTERNAL,
            context=parent_ctx,
            attributes=attributes or {},
        )

        if self.session_id:
            span.set_attribute("session.id", self.session_id)

        self._spans[run_id] = span
        token = trace.context_api.attach(trace.set_span_in_context(span))
        self._tokens[run_id] = token
        return span

    def _end_span(self, run_id: UUID, status: StatusCode = StatusCode.OK) -> None:
        span = self._spans.pop(run_id, None)
        token = self._tokens.pop(run_id, None)
        if span:
            span.set_status(Status(status))
            span.end()
        if token:
            trace.context_api.detach(token)

    # --- Chain callbacks ---

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ) -> None:
        name = serialized.get("name", serialized.get("id", ["unknown"])[-1])
        self._start_span(
            run_id,
            f"chain.run:{name}",
            parent_run_id,
            {"chain.name": name, "chain.input": _truncate(inputs)},
        )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        span = self._spans.get(run_id)
        if span:
            span.set_attribute("chain.output", _truncate(outputs))
        self._end_span(run_id)

    def on_chain_error(
        self, error: BaseException, *, run_id: UUID, **kwargs
    ) -> None:
        span = self._spans.get(run_id)
        if span:
            span.record_exception(error)
        self._end_span(run_id, StatusCode.ERROR)

    # --- LLM callbacks ---

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ) -> None:
        model = kwargs.get("invocation_params", {}).get("model_name", "unknown")
        self._start_span(
            run_id,
            f"llm.call:{model}",
            parent_run_id,
            {
                "gen_ai.system": serialized.get("name", "unknown"),
                "gen_ai.request.model": model,
            },
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        span = self._spans.get(run_id)
        if span and response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            if "prompt_tokens" in token_usage:
                span.set_attribute("gen_ai.usage.input_tokens", token_usage["prompt_tokens"])
            if "completion_tokens" in token_usage:
                span.set_attribute("gen_ai.usage.output_tokens", token_usage["completion_tokens"])
            if "total_tokens" in token_usage:
                span.set_attribute("gen_ai.usage.total_tokens", token_usage["total_tokens"])
            if "model_name" in response.llm_output:
                span.set_attribute("gen_ai.response.model", response.llm_output["model_name"])
        self._end_span(run_id)

    def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs
    ) -> None:
        span = self._spans.get(run_id)
        if span:
            span.record_exception(error)
        self._end_span(run_id, StatusCode.ERROR)

    # --- Tool callbacks ---

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        self._start_span(
            run_id,
            f"tool.call:{tool_name}",
            parent_run_id,
            {"tool.name": tool_name, "tool.input": _truncate(input_str)},
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        **kwargs,
    ) -> None:
        span = self._spans.get(run_id)
        if span:
            span.set_attribute("tool.output", _truncate(output))
        self._end_span(run_id)

    def on_tool_error(
        self, error: BaseException, *, run_id: UUID, **kwargs
    ) -> None:
        span = self._spans.get(run_id)
        if span:
            span.record_exception(error)
        self._end_span(run_id, StatusCode.ERROR)
```

### Integration

```python
from src.observability.langchain_callbacks import OTELCallbackHandler

handler = OTELCallbackHandler(session_id="user-123")

# With chains
result = chain.invoke(
    {"question": "What is the best price?"},
    config={"callbacks": [handler]},
)

# With agents
agent_executor = AgentExecutor(agent=agent, tools=tools)
result = agent_executor.invoke(
    {"input": "Find me a deal"},
    config={"callbacks": [handler]},
)
```

---

## Custom Agent Loop (Generic)

For hand-rolled agent loops without a framework.

### Agent Loop Wrapper

```python
"""
OTEL instrumentation for custom agent loops.
Wrap your agent's main loop with traced_agent_run().
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from opentelemetry import trace
from opentelemetry.trace import StatusCode, Status, SpanKind

from src.telemetry import get_tracer

tracer = get_tracer("custom-agent")

_MAX_ATTR_LENGTH = 1024


def _truncate(value, max_length=_MAX_ATTR_LENGTH):
    s = str(value)
    return s[:max_length] + "...[truncated]" if len(s) > max_length else s


@asynccontextmanager
async def traced_agent_run(
    agent_name: str,
    session_id: Optional[str] = None,
) -> AsyncGenerator[trace.Span, None]:
    """
    Context manager for wrapping an entire agent run.

    Usage:
        async with traced_agent_run("search_agent", session_id="123") as span:
            # Your agent logic here
            result = await run_agent(...)
            span.set_attribute("agent.output", str(result))
    """
    with tracer.start_as_current_span(
        f"agent.run:{agent_name}",
        kind=SpanKind.INTERNAL,
        attributes={"agent.name": agent_name},
    ) as span:
        if session_id:
            span.set_attribute("session.id", session_id)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


@asynccontextmanager
async def traced_llm_call(
    model: str,
    system: str = "openai",
) -> AsyncGenerator[trace.Span, None]:
    """
    Context manager for wrapping an LLM call.

    Usage:
        async with traced_llm_call("gpt-4o") as span:
            response = await client.chat.completions.create(...)
            span.set_attribute("gen_ai.usage.input_tokens", response.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
    """
    with tracer.start_as_current_span(
        f"llm.call:{model}",
        kind=SpanKind.CLIENT,
        attributes={
            "gen_ai.system": system,
            "gen_ai.request.model": model,
        },
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


@asynccontextmanager
async def traced_tool_call(
    tool_name: str,
    tool_input: str = "",
) -> AsyncGenerator[trace.Span, None]:
    """
    Context manager for wrapping a tool call.

    Usage:
        async with traced_tool_call("web_search", "best price for...") as span:
            result = await search(query)
            span.set_attribute("tool.output", str(result)[:1024])
    """
    with tracer.start_as_current_span(
        f"tool.call:{tool_name}",
        kind=SpanKind.INTERNAL,
        attributes={
            "tool.name": tool_name,
            "tool.input": _truncate(tool_input),
        },
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
```

### Usage in a Custom Agent Loop

```python
async def run_my_agent(user_input: str, session_id: str):
    async with traced_agent_run("my_agent", session_id=session_id) as agent_span:
        agent_span.set_attribute("agent.input", user_input)

        # Step 1: Call LLM
        async with traced_llm_call("gpt-4o") as llm_span:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": user_input}],
            )
            llm_span.set_attribute(
                "gen_ai.usage.input_tokens", response.usage.prompt_tokens
            )
            llm_span.set_attribute(
                "gen_ai.usage.output_tokens", response.usage.completion_tokens
            )

        # Step 2: Execute tools if needed
        for tool_call in response.choices[0].message.tool_calls or []:
            async with traced_tool_call(
                tool_call.function.name,
                tool_call.function.arguments,
            ) as tool_span:
                result = await execute_tool(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                tool_span.set_attribute("tool.output", _truncate(result))

        agent_span.set_attribute("agent.output", _truncate(response))
        return response
```

---

## Parallel Tool Calls

OTEL handles parallel spans natively. Just start multiple spans under the same parent:

```python
import asyncio

async def execute_parallel_tools(tool_calls: list, parent_span: Span):
    """Execute multiple tool calls in parallel, each with its own span."""

    async def run_tool(tool_call):
        async with traced_tool_call(
            tool_call.function.name,
            tool_call.function.arguments,
        ) as span:
            result = await execute_tool(
                tool_call.function.name,
                tool_call.function.arguments,
            )
            span.set_attribute("tool.output", _truncate(result))
            return result

    # All tool calls run in parallel, each gets its own span
    # under the current parent context
    results = await asyncio.gather(*[run_tool(tc) for tc in tool_calls])
    return results
```

---

## Node.js / TypeScript Agent Instrumentation

For TypeScript-based agent frameworks:

```typescript
import { getTracer } from './telemetry';
import { SpanStatusCode, SpanKind, type Span, context, trace } from '@opentelemetry/api';

const tracer = getTracer('agents');
const MAX_ATTR_LENGTH = 1024;

function truncate(value: any): string {
  const s = String(value);
  return s.length > MAX_ATTR_LENGTH ? s.slice(0, MAX_ATTR_LENGTH) + '...[truncated]' : s;
}

/**
 * Wrap an agent run in a traced span.
 */
export async function tracedAgentRun<T>(
  agentName: string,
  sessionId: string | undefined,
  fn: (span: Span) => Promise<T>,
): Promise<T> {
  return tracer.startActiveSpan(
    `agent.run:${agentName}`,
    { kind: SpanKind.INTERNAL },
    async (span) => {
      span.setAttribute('agent.name', agentName);
      if (sessionId) span.setAttribute('session.id', sessionId);

      try {
        const result = await fn(span);
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
}

/**
 * Wrap an LLM call in a traced span.
 */
export async function tracedLLMCall<T>(
  model: string,
  fn: (span: Span) => Promise<T>,
): Promise<T> {
  return tracer.startActiveSpan(
    `llm.call:${model}`,
    { kind: SpanKind.CLIENT },
    async (span) => {
      span.setAttribute('gen_ai.system', 'openai');
      span.setAttribute('gen_ai.request.model', model);

      try {
        const result = await fn(span);
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
}

/**
 * Wrap a tool call in a traced span.
 */
export async function tracedToolCall<T>(
  toolName: string,
  toolInput: string,
  fn: (span: Span) => Promise<T>,
): Promise<T> {
  return tracer.startActiveSpan(
    `tool.call:${toolName}`,
    { kind: SpanKind.INTERNAL },
    async (span) => {
      span.setAttribute('tool.name', toolName);
      span.setAttribute('tool.input', truncate(toolInput));

      try {
        const result = await fn(span);
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
}
```

---

## End-to-End Session Flow

The full trace flow from frontend to agent:

```
Frontend (browser)
  └── fetch /api/search  [traceparent: 00-<traceId>-<spanId>-01]
        │
Backend (FastAPI/Express)
  └── HTTP request span (auto-instrumented, extracts traceparent)
        ├── session.id = "user-123" (from X-Session-Id header)
        └── Agent Run: "search_agent"
              ├── LLM Call: "gpt-4o" (tokens: 150/89)
              ├── Tool Call: "web_search" (input: "best price...")
              ├── LLM Call: "gpt-4o" (second call with tool result)
              └── Agent Handoff → "pricing_agent"
                    ├── LLM Call: "gpt-4o-mini"
                    └── Tool Call: "calculate_price"
```

All spans share the same `traceId`, forming a complete distributed trace visible in Jaeger/Tempo.
