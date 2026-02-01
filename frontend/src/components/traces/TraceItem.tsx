/**
 * TraceItem component for displaying a single trace in the list.
 */

import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/Badge';
import { formatDate, truncate } from '@/lib/utils';
import type { Trace } from '@/lib/types';

interface TraceItemProps {
  trace: Trace;
  isSelected: boolean;
  onClick: () => void;
  onDelete: () => void;
  childCount?: number;  // Number of child traces (refinements)
  isChild?: boolean;    // Whether this is a child trace
}

export function TraceItem({ trace, isSelected, onClick, onDelete, childCount, isChild }: TraceItemProps) {
  const statusVariant =
    trace.status === 'completed'
      ? 'success'
      : trace.status === 'error'
      ? 'error'
      : 'warning';

  // Count running spans to show progress
  const runningSpans = trace.spans?.filter(s => s.status === 'running') || [];

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm('Delete this trace?')) {
      onDelete();
    }
  };

  return (
    <div
      data-testid="trace-item"
      className={cn(
        'p-3 rounded-lg cursor-pointer transition-colors relative group',
        'hover:bg-slate-700',
        isSelected ? 'bg-slate-700 border border-cyan-500/50' : 'bg-slate-800',
        trace.status === 'running' && 'border-l-2 border-l-amber-500',
        isChild && 'py-2 text-sm'  // Smaller padding for child traces
      )}
      onClick={onClick}
    >
      {/* Delete button */}
      <button
        onClick={handleDelete}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-500/20 rounded text-red-400 text-xs"
        title="Delete trace"
      >
        ✕
      </button>

      <div className="flex items-start justify-between gap-2 mb-2 pr-6">
        <div className="flex items-center gap-2">
          <Badge variant={statusVariant}>
            {trace.status === 'running' ? (
              <span className="flex items-center gap-1">
                <span className="animate-pulse">●</span> Running
              </span>
            ) : (
              trace.status
            )}
          </Badge>
          {isChild && (
            <span className="text-xs text-slate-400 italic">refinement</span>
          )}
          {childCount && childCount > 0 && (
            <span className="text-xs text-slate-400">
              +{childCount} refinement{childCount > 1 ? 's' : ''}
            </span>
          )}
        </div>
        <span className="text-xs text-slate-400">
          {formatDate(trace.started_at)}
        </span>
      </div>

      <p className={cn("text-white mb-2", isChild ? "text-xs" : "text-sm")}>
        {truncate(trace.input_prompt, isChild ? 60 : 80)}
      </p>

      <div className="flex items-center gap-3 text-xs text-slate-400">
        <span className="font-mono">{trace.id.substring(0, 8)}</span>
        {trace.status === 'running' && runningSpans.length > 0 && (
          <span className="text-amber-400 animate-pulse">
            {runningSpans[0]?.name || 'Processing...'}
          </span>
        )}
        {trace.status === 'completed' && trace.total_tokens > 0 && (
          <span>{trace.total_tokens} tokens</span>
        )}
      </div>
    </div>
  );
}
