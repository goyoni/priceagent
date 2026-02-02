/**
 * SpanList component for displaying trace spans with nested DAG visualization.
 * Uses parent_span_id to show hierarchical tool calls and parallel execution.
 */

'use client';

import { useState, useMemo } from 'react';
import { Badge } from '@/components/ui/Badge';
import { formatDuration } from '@/lib/utils';
import type { Span } from '@/lib/types';

interface SpanListProps {
  spans: Span[];
}

interface SpanNode {
  span: Span;
  children: SpanNode[];
  depth: number;
}

// Check if a span is a progress event (has emoji in name)
function isProgressEvent(span: Span): boolean {
  const name = span.name || '';
  return /^[📦🔍✅⚠️❌🔄🎯ℹ️]/.test(name);
}

// Build a tree structure from flat spans using parent_span_id
function buildSpanTree(spans: Span[]): SpanNode[] {
  const spanMap = new Map<string, SpanNode>();
  const roots: SpanNode[] = [];

  // First pass: create nodes for all spans
  spans.forEach(span => {
    const id = span.id || span.span_id || '';
    spanMap.set(id, { span, children: [], depth: 0 });
  });

  // Second pass: build parent-child relationships
  spans.forEach(span => {
    const id = span.id || span.span_id || '';
    const node = spanMap.get(id);
    if (!node) return;

    const parentId = span.parent_span_id;
    if (parentId && spanMap.has(parentId)) {
      const parent = spanMap.get(parentId)!;
      parent.children.push(node);
      node.depth = parent.depth + 1;
    } else {
      roots.push(node);
    }
  });

  // Sort children by start time to show execution order
  const sortChildren = (node: SpanNode) => {
    node.children.sort((a, b) => {
      const aTime = a.span.started_at ? new Date(a.span.started_at).getTime() : 0;
      const bTime = b.span.started_at ? new Date(b.span.started_at).getTime() : 0;
      return aTime - bTime;
    });
    node.children.forEach(sortChildren);
  };

  // Sort roots and all children
  roots.sort((a, b) => {
    const aTime = a.span.started_at ? new Date(a.span.started_at).getTime() : 0;
    const bTime = b.span.started_at ? new Date(b.span.started_at).getTime() : 0;
    return aTime - bTime;
  });
  roots.forEach(sortChildren);

  // Update depths recursively
  const updateDepths = (node: SpanNode, depth: number) => {
    node.depth = depth;
    node.children.forEach(child => updateDepths(child, depth + 1));
  };
  roots.forEach(root => updateDepths(root, 0));

  return roots;
}

// Check if spans are running in parallel (overlapping time)
function areParallel(span1: Span, span2: Span): boolean {
  if (!span1.started_at || !span2.started_at) return false;
  const start1 = new Date(span1.started_at).getTime();
  const start2 = new Date(span2.started_at).getTime();
  const end1 = span1.ended_at ? new Date(span1.ended_at).getTime() : Date.now();
  const end2 = span2.ended_at ? new Date(span2.ended_at).getTime() : Date.now();

  // Check for overlap
  return start1 < end2 && start2 < end1;
}

// Compact progress event display
function ProgressEvent({ span, depth = 0 }: { span: Span; depth?: number }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const spanStatus = span.status || 'completed';

  // Extract emoji and text from name
  const name = span.name || '';
  const emoji = name.match(/^[📦🔍✅⚠️❌🔄🎯ℹ️]/)?.[0] || '•';
  const text = name.replace(/^[📦🔍✅⚠️❌🔄🎯ℹ️]\s*/, '');

  // Determine status color
  const statusColor = spanStatus === 'running'
    ? 'text-warning'
    : name.startsWith('✅')
      ? 'text-success'
      : name.startsWith('❌')
        ? 'text-error'
        : name.startsWith('⚠️')
          ? 'text-warning'
          : 'text-slate-400';

  return (
    <div
      className="border-l-2 border-slate-600 pl-3 py-1"
      style={{ marginLeft: depth * 16 }}
    >
      <div
        className="flex items-start gap-2 cursor-pointer hover:bg-slate-700-hover rounded px-1 -ml-1"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="text-base">{emoji}</span>
        <div className="flex-1 min-w-0">
          <span className={`text-sm font-medium ${statusColor}`}>{text}</span>
          {spanStatus === 'running' && (
            <span className="ml-2 text-xs text-warning animate-pulse">running...</span>
          )}
        </div>
        <span className="text-xs text-slate-400 shrink-0">
          {formatDuration(span.duration_ms || 0)}
        </span>
      </div>

      {isExpanded && span.tool_output && (
        <div className="mt-1 ml-6 text-xs bg-slate-700 rounded p-2 whitespace-pre-wrap font-mono max-h-32 overflow-y-auto">
          {typeof span.tool_output === 'string'
            ? span.tool_output
            : JSON.stringify(span.tool_output, null, 2)}
        </div>
      )}
    </div>
  );
}

interface NestedSpanItemProps {
  node: SpanNode;
  isParallel?: boolean;
}

function NestedSpanItem({ node, isParallel = false }: NestedSpanItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { span, children, depth } = node;

  // Handle missing type/status with defaults - API returns span_type, not type
  const spanType = span.type || span.span_type || 'function';
  const spanStatus = span.status || 'completed';

  const typeVariant = ({
    llm_call: 'primary',
    tool_call: 'success',
    agent_run: 'info',
    handoff: 'warning',
    function: 'secondary',
    agent: 'info',
    tool: 'success',
  } as Record<string, string>)[spanType] || 'secondary';

  const statusVariant = ({
    running: 'warning',
    completed: 'success',
    error: 'error',
  } as Record<string, string>)[spanStatus] || 'success';

  const formatInput = (input: unknown): string => {
    if (!input) return '';
    if (typeof input === 'string') return input;
    try {
      return JSON.stringify(input, null, 2);
    } catch {
      return String(input);
    }
  };

  // Determine which children are running in parallel
  const childrenWithParallel = children.map((child, idx) => {
    const hasParallelSibling = children.some((other, otherIdx) =>
      idx !== otherIdx && areParallel(child.span, other.span)
    );
    return { node: child, isParallel: hasParallelSibling };
  });

  // Nesting visual indicators
  const nestingColors = [
    'border-cyan-500/50',
    'border-purple-500/50',
    'border-amber-500/50',
    'border-green-500/50',
    'border-pink-500/50',
  ];
  const borderColor = nestingColors[depth % nestingColors.length];

  return (
    <div
      className={`relative ${depth > 0 ? `ml-4 border-l-2 ${borderColor} pl-3` : ''}`}
    >
      {/* Parallel indicator */}
      {isParallel && (
        <div className="absolute -left-1 top-4 w-2 h-2 rounded-full bg-cyan-400" title="Running in parallel" />
      )}

      <div className="bg-slate-700 rounded-lg overflow-hidden mb-2">
        {/* Span Header */}
        <div
          className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-700-hover"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-2">
            {/* Nesting depth indicator */}
            {depth > 0 && (
              <span className="text-xs text-slate-400 opacity-50">L{depth}</span>
            )}
            <Badge variant={typeVariant as 'primary' | 'success' | 'info' | 'warning' | 'error' | 'secondary'} className="text-xs uppercase">
              {spanType.replace('_', ' ')}
            </Badge>
            <span className="font-medium">{span.name || 'Unknown'}</span>
            {span.cached === true && (
              <span className="text-xs text-slate-400">(Cached)</span>
            )}
            {children.length > 0 && (
              <span className="text-xs text-cyan-400">
                ({children.length} child{children.length > 1 ? 'ren' : ''})
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-sm">
            {span.input_tokens !== undefined && (
              <span className="text-slate-400">{span.input_tokens} in</span>
            )}
            {span.output_tokens !== undefined && (
              <span className="text-slate-400">{span.output_tokens} out</span>
            )}
            {span.cached !== null && span.cached !== undefined && (
              <Badge variant={span.cached ? 'secondary' : 'info'}>
                {span.cached ? 'CACHED' : 'FRESH'}
              </Badge>
            )}
            <span className="text-slate-400">
              {formatDuration(span.duration_ms || 0)}
            </span>
            <Badge variant={statusVariant as 'warning' | 'success' | 'error'}>{spanStatus}</Badge>
            <span className="text-slate-400">{isExpanded ? '▼' : '▶'}</span>
          </div>
        </div>

        {/* Span Content (expanded) */}
        {isExpanded && (
          <div className="px-4 py-3 bg-slate-800 border-t border-slate-600 space-y-3">
            {/* Parent span info */}
            {span.parent_span_id && (
              <div className="text-xs text-slate-400">
                Parent: <span className="font-mono">{span.parent_span_id.slice(0, 8)}...</span>
              </div>
            )}

            {span.system_prompt && (
              <div>
                <div className="text-xs text-slate-400 uppercase mb-1">
                  System Prompt
                </div>
                <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {span.system_prompt}
                </pre>
              </div>
            )}

            {span.input_messages != null && (
              <div>
                <div className="text-xs text-slate-400 uppercase mb-1">
                  Input Messages
                </div>
                <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {formatInput(span.input_messages)}
                </pre>
              </div>
            )}

            {span.output_content && (
              <div>
                <div className="text-xs text-slate-400 uppercase mb-1">Output</div>
                <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {typeof span.output_content === 'string'
                    ? span.output_content
                    : JSON.stringify(span.output_content, null, 2)}
                </pre>
              </div>
            )}

            {span.tool_input != null && (
              <div>
                <div className="text-xs text-slate-400 uppercase mb-1">
                  Tool Input
                </div>
                <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {formatInput(span.tool_input)}
                </pre>
              </div>
            )}

            {span.tool_output && (
              <div>
                <div className="text-xs text-slate-400 uppercase mb-1">
                  Tool Output
                </div>
                <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                  {typeof span.tool_output === 'string'
                    ? span.tool_output.slice(0, 2000)
                    : JSON.stringify(span.tool_output, null, 2).slice(0, 2000)}
                  {typeof span.tool_output === 'string' && span.tool_output.length > 2000 && '...'}
                </pre>
              </div>
            )}

            {span.error && (
              <div>
                <div className="text-xs text-error uppercase mb-1">Error</div>
                <pre className="text-sm bg-error/10 text-error p-3 rounded overflow-x-auto whitespace-pre-wrap">
                  {span.error}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Render children */}
      {children.length > 0 && (
        <div className="space-y-1">
          {childrenWithParallel.map(({ node: childNode, isParallel: childParallel }, idx) => (
            <NestedSpanItem
              key={childNode.span.id || childNode.span.span_id || idx}
              node={childNode}
              isParallel={childParallel}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Flat span item for legacy view
function SpanItem({ span, index }: { span: Span; index: number }) {
  const [isExpanded, setIsExpanded] = useState(false);

  const spanType = span.type || span.span_type || 'function';
  const spanStatus = span.status || 'completed';

  const typeVariant = ({
    llm_call: 'primary',
    tool_call: 'success',
    agent_run: 'info',
    handoff: 'warning',
    function: 'secondary',
    agent: 'info',
    tool: 'success',
  } as Record<string, string>)[spanType] || 'secondary';

  const statusVariant = ({
    running: 'warning',
    completed: 'success',
    error: 'error',
  } as Record<string, string>)[spanStatus] || 'success';

  const formatInput = (input: unknown): string => {
    if (!input) return '';
    if (typeof input === 'string') return input;
    try {
      return JSON.stringify(input, null, 2);
    } catch {
      return String(input);
    }
  };

  return (
    <div className="bg-slate-700 rounded-lg overflow-hidden">
      <div
        className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-slate-700-hover"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Badge variant={typeVariant as 'primary' | 'success' | 'info' | 'warning' | 'error' | 'secondary'} className="text-xs uppercase">
            {spanType.replace('_', ' ')}
          </Badge>
          <span className="font-medium">{span.name || 'Unknown'}</span>
          {span.cached === true && (
            <span className="text-xs text-slate-400">(Cached)</span>
          )}
        </div>

        <div className="flex items-center gap-3 text-sm">
          {span.input_tokens !== undefined && (
            <span className="text-slate-400">{span.input_tokens} in</span>
          )}
          {span.output_tokens !== undefined && (
            <span className="text-slate-400">{span.output_tokens} out</span>
          )}
          <span className="text-slate-400">
            {formatDuration(span.duration_ms || 0)}
          </span>
          <Badge variant={statusVariant as 'warning' | 'success' | 'error'}>{spanStatus}</Badge>
          <span className="text-slate-400">{isExpanded ? '▼' : '▶'}</span>
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 py-3 bg-slate-800 border-t border-slate-600 space-y-3">
          {span.system_prompt && (
            <div>
              <div className="text-xs text-slate-400 uppercase mb-1">System Prompt</div>
              <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {span.system_prompt}
              </pre>
            </div>
          )}
          {span.tool_input != null && (
            <div>
              <div className="text-xs text-slate-400 uppercase mb-1">Tool Input</div>
              <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {formatInput(span.tool_input)}
              </pre>
            </div>
          )}
          {span.tool_output && (
            <div>
              <div className="text-xs text-slate-400 uppercase mb-1">Tool Output</div>
              <pre className="text-sm bg-slate-700 p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {typeof span.tool_output === 'string'
                  ? span.tool_output.slice(0, 2000)
                  : JSON.stringify(span.tool_output, null, 2).slice(0, 2000)}
              </pre>
            </div>
          )}
          {span.error && (
            <div>
              <div className="text-xs text-error uppercase mb-1">Error</div>
              <pre className="text-sm bg-error/10 text-error p-3 rounded overflow-x-auto whitespace-pre-wrap">
                {span.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function SpanList({ spans }: SpanListProps) {
  const [viewMode, setViewMode] = useState<'nested' | 'flat'>('nested');

  const { progressEvents, regularSpans, spanTree } = useMemo(() => {
    const progress = spans.filter(isProgressEvent);
    const regular = spans.filter(s => !isProgressEvent(s));
    const tree = buildSpanTree(regular);
    return { progressEvents: progress, regularSpans: regular, spanTree: tree };
  }, [spans]);

  if (!spans || spans.length === 0) {
    return (
      <div className="text-slate-400 text-sm py-4">No spans recorded</div>
    );
  }

  // Check if we have any nesting (any span has parent_span_id)
  const hasNesting = regularSpans.some(s => s.parent_span_id);

  return (
    <div className="space-y-4">
      {/* View Mode Toggle */}
      {hasNesting && regularSpans.length > 0 && (
        <div className="flex items-center justify-end gap-2">
          <span className="text-xs text-slate-400">View:</span>
          <button
            onClick={() => setViewMode('nested')}
            className={`px-2 py-1 text-xs rounded ${
              viewMode === 'nested'
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'bg-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            Nested
          </button>
          <button
            onClick={() => setViewMode('flat')}
            className={`px-2 py-1 text-xs rounded ${
              viewMode === 'flat'
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'bg-slate-700 text-slate-400 hover:text-white'
            }`}
          >
            Flat
          </button>
        </div>
      )}

      {/* Progress Timeline (if any) */}
      {progressEvents.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-2">
            Activity Timeline ({progressEvents.length} events)
          </h3>
          <div className="bg-slate-700 rounded-lg p-3 space-y-0">
            {progressEvents.map((span, idx) => (
              <ProgressEvent key={span.id || span.span_id || idx} span={span} />
            ))}
          </div>
        </div>
      )}

      {/* Regular Spans */}
      {regularSpans.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-2">
            Trace Details ({regularSpans.length} spans)
            {hasNesting && viewMode === 'nested' && (
              <span className="ml-2 text-xs text-cyan-400">
                • nested view
              </span>
            )}
          </h3>

          {viewMode === 'nested' && hasNesting ? (
            <div className="space-y-2">
              {spanTree.map((node, idx) => (
                <NestedSpanItem
                  key={node.span.id || node.span.span_id || idx}
                  node={node}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {regularSpans.map((span, idx) => (
                <SpanItem key={span.id || span.span_id || idx} span={span} index={idx} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      {hasNesting && viewMode === 'nested' && (
        <div className="text-xs text-slate-400 flex items-center gap-4 pt-2 border-t border-slate-600">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
            Parallel execution
          </span>
          <span className="flex items-center gap-1">
            <span className="border-l-2 border-cyan-500/50 h-3"></span>
            Child of parent span
          </span>
        </div>
      )}
    </div>
  );
}
