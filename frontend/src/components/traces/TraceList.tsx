/**
 * TraceList component for displaying the list of traces.
 */

'use client';

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useTraceStore } from '@/stores/useTraceStore';
import { TraceItem } from './TraceItem';

export function TraceList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [expandedTraces, setExpandedTraces] = useState<Set<string>>(new Set());

  const {
    traces,
    selectedTraceId,
    selectTrace,
    fetchTraces,
    fetchTraceDetail,
    deleteTrace,
    isLoading,
    error,
  } = useTraceStore();

  const hasRunningTraces = (traces || []).some(t => t.status === 'running');

  // Handle trace selection with URL update
  const handleSelectTrace = (traceId: string) => {
    selectTrace(traceId);
    // Update URL
    const params = new URLSearchParams(searchParams.toString());
    params.set('trace', traceId);
    router.push(`/dashboard?${params.toString()}`, { scroll: false });
  };

  // Toggle expanded state for traces with children
  const toggleExpanded = (traceId: string) => {
    setExpandedTraces(prev => {
      const next = new Set(prev);
      if (next.has(traceId)) {
        next.delete(traceId);
      } else {
        next.add(traceId);
      }
      return next;
    });
  };

  // Read trace from URL on mount
  useEffect(() => {
    const traceId = searchParams.get('trace');
    if (traceId && traceId !== selectedTraceId) {
      selectTrace(traceId);
    }
  }, [searchParams, selectTrace, selectedTraceId]);

  // Initial load and polling
  useEffect(() => {
    fetchTraces();

    // Poll faster when traces are running (2s), slower otherwise (5s)
    const pollInterval = hasRunningTraces ? 2000 : 5000;
    const interval = setInterval(fetchTraces, pollInterval);
    return () => clearInterval(interval);
  }, [fetchTraces, hasRunningTraces]);

  // Also refresh selected trace detail more frequently when running
  useEffect(() => {
    if (!selectedTraceId || !traces) return;

    const selectedTrace = traces.find(t => t.id === selectedTraceId);
    if (selectedTrace?.status !== 'running') return;

    // Refresh trace detail every 2 seconds while running
    const interval = setInterval(() => {
      fetchTraceDetail(selectedTraceId);
    }, 2000);

    return () => clearInterval(interval);
  }, [selectedTraceId, traces, fetchTraceDetail]);

  if (error) {
    return (
      <div className="p-4 text-center text-error">
        <p>Error loading traces</p>
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (isLoading && (!traces || traces.length === 0)) {
    return (
      <div className="p-4 text-center text-secondary">
        <p>Loading traces...</p>
      </div>
    );
  }

  if (!traces || traces.length === 0) {
    return (
      <div className="p-8 text-center text-secondary">
        <p className="text-lg mb-2">No traces yet</p>
        <p className="text-sm">Run a search to see traces here</p>
      </div>
    );
  }

  return (
    <div className="space-y-2 p-2">
      {traces.map((trace) => {
        const hasChildren = trace.child_traces && trace.child_traces.length > 0;
        const isExpanded = expandedTraces.has(trace.id);

        return (
          <div key={trace.id}>
            <div className="flex items-start gap-1">
              {/* Expand/collapse button for traces with children */}
              {hasChildren && (
                <button
                  onClick={() => toggleExpanded(trace.id)}
                  className="mt-3 p-1 text-secondary hover:text-primary transition-colors text-xs"
                  title={isExpanded ? 'Collapse' : 'Expand'}
                >
                  {isExpanded ? '▼' : '▶'}
                </button>
              )}
              {!hasChildren && <div className="w-5" />}

              <div className="flex-1">
                <TraceItem
                  trace={trace}
                  isSelected={trace.id === selectedTraceId}
                  onClick={() => handleSelectTrace(trace.id)}
                  onDelete={() => deleteTrace(trace.id)}
                  childCount={trace.child_traces?.length}
                />
              </div>
            </div>

            {/* Nested child traces */}
            {hasChildren && isExpanded && (
              <div className="ml-6 mt-1 space-y-1 border-l-2 border-gray-300 pl-2">
                {trace.child_traces!.map((child) => (
                  <TraceItem
                    key={child.id}
                    trace={child}
                    isSelected={child.id === selectedTraceId}
                    onClick={() => handleSelectTrace(child.id)}
                    onDelete={() => deleteTrace(child.id)}
                    isChild
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
