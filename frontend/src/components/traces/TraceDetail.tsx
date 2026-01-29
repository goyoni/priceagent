/**
 * TraceDetail component for displaying trace details with search results.
 */

'use client';

import { useTraceStore } from '@/stores/useTraceStore';
import { Badge } from '@/components/ui/Badge';
import { SearchResults } from '@/components/search/SearchResults';
import { SpanList } from './SpanList';
import { formatDate, formatDuration } from '@/lib/utils';

export function TraceDetail() {
  const { selectedTrace, selectedTraceId, isLoading } = useTraceStore();

  if (!selectedTraceId) {
    return (
      <div className="h-full flex items-center justify-center text-secondary">
        <p>Select a trace to view details</p>
      </div>
    );
  }

  if (isLoading && !selectedTrace) {
    return (
      <div className="h-full flex items-center justify-center text-secondary">
        <p>Loading trace details...</p>
      </div>
    );
  }

  if (!selectedTrace) {
    return (
      <div className="h-full flex items-center justify-center text-error">
        <p>Trace not found</p>
      </div>
    );
  }

  const statusVariant =
    selectedTrace.status === 'completed'
      ? 'success'
      : selectedTrace.status === 'error'
      ? 'error'
      : 'warning';

  // Get running span info for progress display
  const runningSpans = selectedTrace.spans?.filter(s => s.status === 'running') || [];
  const completedSpans = selectedTrace.spans?.filter(s => s.status === 'completed') || [];
  const completedToolSpans = selectedTrace.spans?.filter(
    s => s.status === 'completed' && s.span_type === 'tool_call' && s.tool_output
  ) || [];
  const totalSpans = selectedTrace.spans?.length || 0;

  // Format tool output for display
  const formatToolOutput = (output: unknown): string => {
    if (!output) return '';
    if (typeof output === 'string') {
      return output.slice(0, 1000) + (output.length > 1000 ? '...' : '');
    }
    try {
      const str = JSON.stringify(output, null, 2);
      return str.slice(0, 1000) + (str.length > 1000 ? '...' : '');
    } catch {
      return String(output).slice(0, 1000);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Badge variant={statusVariant}>{selectedTrace.status}</Badge>
          <span
            className="text-xs text-secondary font-mono cursor-pointer hover:text-primary"
            onClick={() => navigator.clipboard.writeText(selectedTrace.id)}
            title="Click to copy"
          >
            {selectedTrace.id}
          </span>
        </div>

        <h2 className="text-lg font-semibold mb-2">
          {selectedTrace.input_prompt}
        </h2>

        <div className="flex gap-4 text-sm text-secondary">
          <span>Started: {formatDate(selectedTrace.started_at)}</span>
          {selectedTrace.total_duration_ms > 0 && (
            <span>
              Duration: {formatDuration(selectedTrace.total_duration_ms)}
            </span>
          )}
          {selectedTrace.total_tokens > 0 && (
            <span>Tokens: {selectedTrace.total_tokens}</span>
          )}
        </div>
      </div>

      {/* Operational Summary */}
      {selectedTrace.operational_summary && (
        <details className="mb-6">
          <summary className="text-sm font-medium text-secondary cursor-pointer hover:text-primary flex items-center gap-2">
            <span>Operational Summary</span>
            {selectedTrace.operational_summary.errors?.length > 0 && (
              <Badge variant="error">{selectedTrace.operational_summary.errors.length} errors</Badge>
            )}
            {selectedTrace.operational_summary.warnings?.length > 0 && (
              <Badge variant="warning">{selectedTrace.operational_summary.warnings.length} warnings</Badge>
            )}
          </summary>
          <div className="mt-3 bg-surface rounded-lg p-4 space-y-4">
            {/* Search Stats */}
            <div>
              <h4 className="text-xs font-medium text-secondary uppercase mb-2">Searches</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div className="bg-background rounded p-2">
                  <div className="text-lg font-semibold text-primary">
                    {selectedTrace.operational_summary.google_searches || 0}
                  </div>
                  <div className="text-xs text-secondary">Google Searches</div>
                </div>
                <div className="bg-background rounded p-2">
                  <div className="text-lg font-semibold text-success">
                    {selectedTrace.operational_summary.google_searches_cached || 0}
                  </div>
                  <div className="text-xs text-secondary">Google (Cached)</div>
                </div>
                <div className="bg-background rounded p-2">
                  <div className="text-lg font-semibold text-primary">
                    {selectedTrace.operational_summary.zap_searches || 0}
                  </div>
                  <div className="text-xs text-secondary">Zap Searches</div>
                </div>
                <div className="bg-background rounded p-2">
                  <div className="text-lg font-semibold text-success">
                    {selectedTrace.operational_summary.zap_searches_cached || 0}
                  </div>
                  <div className="text-xs text-secondary">Zap (Cached)</div>
                </div>
              </div>
            </div>

            {/* Scrape Stats */}
            <div>
              <h4 className="text-xs font-medium text-secondary uppercase mb-2">Page Scrapes</h4>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-background rounded p-2">
                  <div className="text-lg font-semibold text-primary">
                    {selectedTrace.operational_summary.page_scrapes || 0}
                  </div>
                  <div className="text-xs text-secondary">Pages Scraped</div>
                </div>
                <div className="bg-background rounded p-2">
                  <div className="text-lg font-semibold text-success">
                    {selectedTrace.operational_summary.page_scrapes_cached || 0}
                  </div>
                  <div className="text-xs text-secondary">Cached</div>
                </div>
              </div>
            </div>

            {/* Extraction Stats */}
            {(selectedTrace.operational_summary.prices_extracted > 0 ||
              selectedTrace.operational_summary.prices_failed > 0) && (
              <div>
                <h4 className="text-xs font-medium text-secondary uppercase mb-2">Extractions</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="bg-background rounded p-2">
                    <div className="text-lg font-semibold text-success">
                      {selectedTrace.operational_summary.prices_extracted || 0}
                    </div>
                    <div className="text-xs text-secondary">Prices Found</div>
                  </div>
                  <div className="bg-background rounded p-2">
                    <div className="text-lg font-semibold text-error">
                      {selectedTrace.operational_summary.prices_failed || 0}
                    </div>
                    <div className="text-xs text-secondary">Prices Failed</div>
                  </div>
                  <div className="bg-background rounded p-2">
                    <div className="text-lg font-semibold text-success">
                      {selectedTrace.operational_summary.contacts_extracted || 0}
                    </div>
                    <div className="text-xs text-secondary">Contacts Found</div>
                  </div>
                  <div className="bg-background rounded p-2">
                    <div className="text-lg font-semibold text-error">
                      {selectedTrace.operational_summary.contacts_failed || 0}
                    </div>
                    <div className="text-xs text-secondary">Contacts Failed</div>
                  </div>
                </div>
              </div>
            )}

            {/* Errors */}
            {selectedTrace.operational_summary.errors?.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-error uppercase mb-2">
                  Errors ({selectedTrace.operational_summary.errors.length})
                </h4>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {selectedTrace.operational_summary.errors.map((err, i) => (
                    <div
                      key={i}
                      className="bg-error/10 text-error text-xs p-2 rounded font-mono"
                    >
                      {err}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Warnings */}
            {selectedTrace.operational_summary.warnings?.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-warning uppercase mb-2">
                  Warnings ({selectedTrace.operational_summary.warnings.length})
                </h4>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {selectedTrace.operational_summary.warnings.map((warn, i) => (
                    <div
                      key={i}
                      className="bg-warning/10 text-warning text-xs p-2 rounded font-mono"
                    >
                      {warn}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </details>
      )}

      {/* Progress indicator for running traces */}
      {selectedTrace.status === 'running' && (
        <div className="mb-6 p-4 bg-warning/10 border border-warning/30 rounded-lg">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-4 h-4 border-2 border-warning border-t-transparent rounded-full animate-spin" />
            <span className="text-warning font-medium">Search in progress...</span>
          </div>
          {runningSpans.length > 0 && (
            <div className="text-sm text-secondary">
              <p>Current: {runningSpans[0]?.name || 'Processing'}</p>
              {runningSpans[0]?.tool_input != null && typeof runningSpans[0].tool_input === 'object' && (
                <p className="text-xs mt-1">
                  {JSON.stringify(runningSpans[0].tool_input).slice(0, 100)}...
                </p>
              )}
            </div>
          )}
          {totalSpans > 0 && (
            <div className="mt-2 text-xs text-secondary">
              Steps completed: {completedSpans.length} / {totalSpans}
            </div>
          )}

          {/* Show completed tool outputs as they come in */}
          {completedToolSpans.length > 0 && (
            <div className="mt-4 border-t border-warning/20 pt-3">
              <p className="text-xs text-secondary mb-2">Results so far:</p>
              <div className="max-h-64 overflow-y-auto space-y-2">
                {completedToolSpans.map((span) => (
                  <div key={span.id} className="bg-background/50 rounded p-2 text-xs">
                    <p className="text-primary font-medium mb-1">{span.name}</p>
                    <pre className="text-secondary whitespace-pre-wrap font-mono text-[10px] max-h-32 overflow-y-auto">
                      {formatToolOutput(span.tool_output)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {selectedTrace.error && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-error mb-2">Error</h3>
          <div className="bg-error/10 border border-error/30 rounded-lg p-4 text-sm text-error">
            {selectedTrace.error}
          </div>
        </div>
      )}

      {/* Search Results Tables */}
      <SearchResults />

      {/* Trace DAG / Spans */}
      {selectedTrace.spans && selectedTrace.spans.length > 0 && (
        <div className="mb-6">
          <SpanList spans={selectedTrace.spans} />
        </div>
      )}

      {/* Final Output - collapsed by default if we have tables */}
      {selectedTrace.final_output && (
        <details className="mb-6">
          <summary className="text-sm font-medium text-secondary mb-2 cursor-pointer hover:text-primary">
            Raw Output
          </summary>
          <div className="bg-background rounded-lg p-4 text-sm whitespace-pre-wrap mt-2">
            {selectedTrace.final_output}
          </div>
        </details>
      )}
    </div>
  );
}
