/**
 * SpanList component for displaying trace spans with DAG visualization.
 */

'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { formatDuration } from '@/lib/utils';
import type { Span } from '@/lib/types';

interface SpanListProps {
  spans: Span[];
}

interface SpanItemProps {
  span: Span;
  index: number;
}

// Check if a span is a progress event (has emoji in name)
function isProgressEvent(span: Span): boolean {
  const name = span.name || '';
  return /^[📦🔍✅⚠️❌🔄🎯ℹ️]/.test(name);
}

// Compact progress event display
function ProgressEvent({ span }: { span: Span }) {
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
          : 'text-secondary';

  return (
    <div className="border-l-2 border-surface-hover pl-3 py-1">
      <div
        className="flex items-start gap-2 cursor-pointer hover:bg-surface-hover rounded px-1 -ml-1"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="text-base">{emoji}</span>
        <div className="flex-1 min-w-0">
          <span className={`text-sm font-medium ${statusColor}`}>{text}</span>
          {spanStatus === 'running' && (
            <span className="ml-2 text-xs text-warning animate-pulse">running...</span>
          )}
        </div>
        <span className="text-xs text-secondary shrink-0">
          {formatDuration(span.duration_ms || 0)}
        </span>
      </div>

      {isExpanded && span.tool_output && (
        <div className="mt-1 ml-6 text-xs bg-surface rounded p-2 whitespace-pre-wrap font-mono max-h-32 overflow-y-auto">
          {typeof span.tool_output === 'string'
            ? span.tool_output
            : JSON.stringify(span.tool_output, null, 2)}
        </div>
      )}
    </div>
  );
}

function SpanItem({ span, index }: SpanItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

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

  return (
    <div className="bg-surface rounded-lg overflow-hidden">
      {/* Span Header */}
      <div
        className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <Badge variant={typeVariant as 'primary' | 'success' | 'info' | 'warning' | 'error' | 'secondary'} className="text-xs uppercase">
            {spanType.replace('_', ' ')}
          </Badge>
          <span className="font-medium">{span.name || 'Unknown'}</span>
          {span.cached === true && (
            <span className="text-xs text-secondary">(Cached)</span>
          )}
        </div>

        <div className="flex items-center gap-3 text-sm">
          {span.input_tokens !== undefined && (
            <span className="text-secondary">{span.input_tokens} in</span>
          )}
          {span.output_tokens !== undefined && (
            <span className="text-secondary">{span.output_tokens} out</span>
          )}
          {span.cached !== null && span.cached !== undefined && (
            <Badge variant={span.cached ? 'secondary' : 'info'}>
              {span.cached ? 'CACHED' : 'FRESH'}
            </Badge>
          )}
          <span className="text-secondary">
            {formatDuration(span.duration_ms || 0)}
          </span>
          <Badge variant={statusVariant as 'warning' | 'success' | 'error'}>{spanStatus}</Badge>
          <span className="text-secondary">{isExpanded ? '▼' : '▶'}</span>
        </div>
      </div>

      {/* Span Content (expanded) */}
      {isExpanded && (
        <div className="px-4 py-3 bg-background border-t border-surface-hover space-y-3">
          {span.system_prompt && (
            <div>
              <div className="text-xs text-secondary uppercase mb-1">
                System Prompt
              </div>
              <pre className="text-sm bg-surface p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {span.system_prompt}
              </pre>
            </div>
          )}

          {span.input_messages != null && (
            <div>
              <div className="text-xs text-secondary uppercase mb-1">
                Input Messages
              </div>
              <pre className="text-sm bg-surface p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {formatInput(span.input_messages)}
              </pre>
            </div>
          )}

          {span.output_content && (
            <div>
              <div className="text-xs text-secondary uppercase mb-1">Output</div>
              <pre className="text-sm bg-surface p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {typeof span.output_content === 'string'
                  ? span.output_content
                  : JSON.stringify(span.output_content, null, 2)}
              </pre>
            </div>
          )}

          {span.tool_input != null && (
            <div>
              <div className="text-xs text-secondary uppercase mb-1">
                Tool Input
              </div>
              <pre className="text-sm bg-surface p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
                {formatInput(span.tool_input)}
              </pre>
            </div>
          )}

          {span.tool_output && (
            <div>
              <div className="text-xs text-secondary uppercase mb-1">
                Tool Output
              </div>
              <pre className="text-sm bg-surface p-3 rounded overflow-x-auto max-h-48 whitespace-pre-wrap">
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
  );
}

export function SpanList({ spans }: SpanListProps) {
  if (!spans || spans.length === 0) {
    return (
      <div className="text-secondary text-sm py-4">No spans recorded</div>
    );
  }

  // Separate progress events from regular spans
  const progressEvents = spans.filter(isProgressEvent);
  const regularSpans = spans.filter(s => !isProgressEvent(s));

  return (
    <div className="space-y-4">
      {/* Progress Timeline (if any) */}
      {progressEvents.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-secondary mb-2">
            Activity Timeline ({progressEvents.length} events)
          </h3>
          <div className="bg-surface rounded-lg p-3 space-y-0">
            {progressEvents.map((span, idx) => (
              <ProgressEvent key={span.id || span.span_id || idx} span={span} />
            ))}
          </div>
        </div>
      )}

      {/* Regular Spans (agent runs, LLM calls, etc) */}
      {regularSpans.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-secondary mb-2">
            Trace Details ({regularSpans.length} spans)
          </h3>
          <div className="space-y-2">
            {regularSpans.map((span, idx) => (
              <SpanItem key={span.id || span.span_id || idx} span={span} index={idx} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
