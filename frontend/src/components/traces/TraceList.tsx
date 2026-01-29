/**
 * TraceList component for displaying the list of traces.
 */

'use client';

import { useEffect } from 'react';
import { useTraceStore } from '@/stores/useTraceStore';
import { TraceItem } from './TraceItem';

export function TraceList() {
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
      {traces.map((trace) => (
        <TraceItem
          key={trace.id}
          trace={trace}
          isSelected={trace.id === selectedTraceId}
          onClick={() => selectTrace(trace.id)}
          onDelete={() => deleteTrace(trace.id)}
        />
      ))}
    </div>
  );
}
