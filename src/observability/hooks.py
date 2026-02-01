"""Observability hooks for capturing agent execution traces."""

import json
from typing import Any, Optional

from agents import Agent
from agents.items import ModelResponse, TResponseInputItem
from agents.lifecycle import RunHooksBase
from agents.run_context import AgentHookContext, RunContextWrapper
from agents.tool import Tool

from src.cache import clear_cache_hit_status, get_cache_hit_status

from .models import OperationalSummary, Span, SpanStatus, SpanType, Trace
from .store import TraceStore, get_trace_store


# Global reference to current hooks instance for progress reporting
_current_hooks: Optional["ObservabilityHooks"] = None


def get_current_hooks() -> Optional["ObservabilityHooks"]:
    """Get the current observability hooks instance."""
    return _current_hooks


async def report_progress(name: str, output: str) -> None:
    """Report progress from within a tool function.

    Creates a completed span with the given name and output.
    Use this to show intermediate results in the UI.

    Args:
        name: Name of the progress step (e.g., "Scraper: google_shopping")
        output: Output/result to display
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    span = Span(
        trace_id=hooks._current_trace_id,
        parent_span_id=hooks._get_parent_span_id(),
        span_type=SpanType.TOOL_CALL,
        name=name,
        tool_name=name,
        tool_output=output,
    )
    await hooks.store.create_span(hooks._current_trace_id, span)
    await hooks.store.complete_span(hooks._current_trace_id, span.id)


async def record_search(source: str, cached: bool = False) -> None:
    """Record a search operation in operational summary.

    Args:
        source: Source of search (e.g., "google", "zap", "google_shopping")
        cached: Whether the result came from cache
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    trace = hooks.store.get_trace(hooks._current_trace_id)
    if not trace:
        return

    if "google" in source.lower():
        if cached:
            trace.operational_summary.google_searches_cached += 1
        else:
            trace.operational_summary.google_searches += 1
    elif "zap" in source.lower():
        if cached:
            trace.operational_summary.zap_searches_cached += 1
        else:
            trace.operational_summary.zap_searches += 1

    await hooks.store.update_trace(hooks._current_trace_id, trace)


async def record_scrape(cached: bool = False) -> None:
    """Record a page scrape operation in operational summary.

    Args:
        cached: Whether the result came from cache
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    trace = hooks.store.get_trace(hooks._current_trace_id)
    if not trace:
        return

    if cached:
        trace.operational_summary.page_scrapes_cached += 1
    else:
        trace.operational_summary.page_scrapes += 1

    await hooks.store.update_trace(hooks._current_trace_id, trace)


async def record_price_extraction(success: bool) -> None:
    """Record a price extraction attempt.

    Args:
        success: Whether the extraction was successful
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    trace = hooks.store.get_trace(hooks._current_trace_id)
    if not trace:
        return

    if success:
        trace.operational_summary.prices_extracted += 1
    else:
        trace.operational_summary.prices_failed += 1

    await hooks.store.update_trace(hooks._current_trace_id, trace)


async def record_contact_extraction(success: bool) -> None:
    """Record a contact extraction attempt.

    Args:
        success: Whether the extraction was successful
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    trace = hooks.store.get_trace(hooks._current_trace_id)
    if not trace:
        return

    if success:
        trace.operational_summary.contacts_extracted += 1
    else:
        trace.operational_summary.contacts_failed += 1

    await hooks.store.update_trace(hooks._current_trace_id, trace)


async def record_error(message: str) -> None:
    """Record an error in operational summary.

    Args:
        message: Error message to record
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    trace = hooks.store.get_trace(hooks._current_trace_id)
    if not trace:
        return

    trace.operational_summary.errors.append(message)
    await hooks.store.update_trace(hooks._current_trace_id, trace)


async def record_warning(message: str) -> None:
    """Record a warning in operational summary.

    Args:
        message: Warning message to record
    """
    hooks = get_current_hooks()
    if not hooks or not hooks._current_trace_id:
        return

    trace = hooks.store.get_trace(hooks._current_trace_id)
    if not trace:
        return

    trace.operational_summary.warnings.append(message)
    await hooks.store.update_trace(hooks._current_trace_id, trace)


class ObservabilityHooks(RunHooksBase):
    """Hooks that capture all agent activities for observability."""

    def __init__(self, store: Optional[TraceStore] = None):
        self.store = store or get_trace_store()
        self._current_trace_id: Optional[str] = None
        self._agent_span_stack: list[str] = []  # Stack of agent span IDs
        self._llm_spans: dict[str, str] = {}  # Map of context hash to span ID
        self._tool_spans: dict[int, str] = {}  # Map of context id to span ID (for correct pairing of parallel calls)

    async def start_trace(self, input_prompt: str, session_id: Optional[str] = None, parent_trace_id: Optional[str] = None) -> Trace:
        """Start a new trace. Call this before Runner.run()."""
        global _current_hooks
        _current_hooks = self

        trace = await self.store.create_trace(input_prompt=input_prompt, session_id=session_id, parent_trace_id=parent_trace_id)
        self._current_trace_id = trace.id
        self._agent_span_stack = []
        self._llm_spans = {}
        self._tool_spans = {}
        return trace

    async def end_trace(self, final_output: Optional[str] = None, error: Optional[str] = None):
        """End the current trace. Call this after Runner.run() completes."""
        global _current_hooks

        if self._current_trace_id:
            await self.store.complete_trace(
                self._current_trace_id,
                final_output=final_output,
                error=error
            )
            self._current_trace_id = None

        _current_hooks = None

    def _get_parent_span_id(self) -> Optional[str]:
        """Get the current parent span ID (top of agent stack)."""
        return self._agent_span_stack[-1] if self._agent_span_stack else None

    def _serialize_input_items(self, input_items: list[TResponseInputItem]) -> list[dict[str, Any]]:
        """Serialize input items to JSON-safe dicts."""
        result = []
        for item in input_items:
            if hasattr(item, 'model_dump'):
                result.append(item.model_dump())
            elif isinstance(item, dict):
                result.append(item)
            else:
                result.append({"type": "unknown", "content": str(item)})
        return result

    def _extract_output_content(self, response: ModelResponse) -> str:
        """Extract text content from model response."""
        contents = []
        for output in response.output:
            if hasattr(output, 'content'):
                for content in output.content:
                    if hasattr(content, 'text'):
                        contents.append(content.text)
            elif hasattr(output, 'model_dump'):
                contents.append(json.dumps(output.model_dump(), default=str))
        return "\n".join(contents) if contents else str(response.output)

    async def on_agent_start(self, context: AgentHookContext, agent: Agent) -> None:
        """Called when an agent starts execution."""
        if not self._current_trace_id:
            return

        span = Span(
            trace_id=self._current_trace_id,
            parent_span_id=self._get_parent_span_id(),
            span_type=SpanType.AGENT_RUN,
            name=agent.name,
        )
        await self.store.create_span(self._current_trace_id, span)
        self._agent_span_stack.append(span.id)

    async def on_agent_end(self, context: AgentHookContext, agent: Agent, output: Any) -> None:
        """Called when an agent produces final output."""
        if not self._current_trace_id or not self._agent_span_stack:
            return

        span_id = self._agent_span_stack.pop()
        output_str = str(output) if output else None

        await self.store.complete_span(
            self._current_trace_id,
            span_id,
            output_content=output_str,
        )

    async def on_llm_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        system_prompt: Optional[str],
        input_items: list[TResponseInputItem],
    ) -> None:
        """Called before LLM invocation."""
        if not self._current_trace_id:
            return

        span = Span(
            trace_id=self._current_trace_id,
            parent_span_id=self._get_parent_span_id(),
            span_type=SpanType.LLM_CALL,
            name=f"LLM: {agent.name}",
            system_prompt=system_prompt,
            input_messages=self._serialize_input_items(input_items),
            model=getattr(agent, 'model', None),
        )
        await self.store.create_span(self._current_trace_id, span)

        # Store span ID keyed by agent name (simple approach)
        self._llm_spans[agent.name] = span.id

    async def on_llm_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        response: ModelResponse,
    ) -> None:
        """Called after LLM invocation."""
        if not self._current_trace_id:
            return

        span_id = self._llm_spans.pop(agent.name, None)
        if not span_id:
            return

        await self.store.complete_span(
            self._current_trace_id,
            span_id,
            output_content=self._extract_output_content(response),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def on_tool_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Tool,
    ) -> None:
        """Called before tool invocation."""
        if not self._current_trace_id:
            return

        # Try to extract tool arguments from ToolContext
        tool_input = None
        if hasattr(context, 'tool_arguments'):
            try:
                tool_input = json.loads(context.tool_arguments)
            except (json.JSONDecodeError, TypeError):
                tool_input = {"raw": str(context.tool_arguments)}

        span = Span(
            trace_id=self._current_trace_id,
            parent_span_id=self._get_parent_span_id(),
            span_type=SpanType.TOOL_CALL,
            name=f"Tool: {tool.name}",
            tool_name=tool.name,
            tool_input=tool_input,
        )
        await self.store.create_span(self._current_trace_id, span)
        # Use context id as unique key to correctly pair start/end for parallel calls
        self._tool_spans[id(context)] = span.id

    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Tool,
        result: str,
    ) -> None:
        """Called after tool invocation."""
        if not self._current_trace_id:
            return

        # Look up span by context id to correctly pair with the start call
        span_id = self._tool_spans.pop(id(context), None)
        if not span_id:
            return

        # Check if this tool call used cache
        cache_status = get_cache_hit_status()
        clear_cache_hit_status()

        await self.store.complete_span(
            self._current_trace_id,
            span_id,
            tool_output=result,
            cached=cache_status,
        )

    async def on_handoff(
        self,
        context: RunContextWrapper,
        from_agent: Agent,
        to_agent: Agent,
    ) -> None:
        """Called when a handoff occurs between agents."""
        if not self._current_trace_id:
            return

        span = Span(
            trace_id=self._current_trace_id,
            parent_span_id=self._get_parent_span_id(),
            span_type=SpanType.HANDOFF,
            name=f"Handoff: {from_agent.name} -> {to_agent.name}",
            from_agent=from_agent.name,
            to_agent=to_agent.name,
        )
        await self.store.create_span(self._current_trace_id, span)

        # Handoff spans are instant, complete immediately
        await self.store.complete_span(self._current_trace_id, span.id)
