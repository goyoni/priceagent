/**
 * LogViewer component for displaying application logs.
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface LogEntry {
  timestamp: string;
  level: string;
  event: string;
  message?: string;
  data: Record<string, unknown>;
}

interface LogResponse {
  logs: LogEntry[];
  total: number;
  has_more: boolean;
}

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-slate-400',
  INFO: 'text-cyan-400',
  WARN: 'text-amber-400',
  WARNING: 'text-amber-400',
  ERROR: 'text-red-400',
};

const LEVEL_BG: Record<string, string> = {
  DEBUG: 'bg-slate-500/20',
  INFO: 'bg-cyan-500/20',
  WARN: 'bg-amber-500/20',
  WARNING: 'bg-amber-500/20',
  ERROR: 'bg-red-500/20',
};

export function LogViewer() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [logFile, setLogFile] = useState<'app' | 'error'>('app');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const params = new URLSearchParams({
        limit: '200',
        file: logFile,
      });

      if (levelFilter) {
        params.append('level', levelFilter);
      }
      if (searchQuery) {
        params.append('search', searchQuery);
      }

      const response = await fetch(`${apiUrl}/api/logs?${params}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data: LogResponse = await response.json();
      setLogs(data.logs);
      setTotal(data.total);
      setHasMore(data.has_more);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs');
    } finally {
      setLoading(false);
    }
  }, [levelFilter, searchQuery, logFile]);

  // Initial fetch and auto-refresh
  useEffect(() => {
    fetchLogs();

    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 3000);
      return () => clearInterval(interval);
    }
  }, [fetchLogs, autoRefresh]);

  const toggleRowExpanded = (index: number) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const formatTimestamp = (ts: string) => {
    try {
      const date = new Date(ts);
      return date.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  const formatDate = (ts: string) => {
    try {
      const date = new Date(ts);
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return '';
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 rounded-lg overflow-hidden">
      {/* Header with filters */}
      <div className="flex items-center gap-3 p-3 border-b border-slate-700 bg-slate-800/50">
        <h3 className="font-medium text-white">Logs</h3>

        {/* Log file toggle */}
        <div className="flex rounded-lg overflow-hidden border border-slate-600">
          <button
            onClick={() => setLogFile('app')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              logFile === 'app'
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'text-slate-400 hover:bg-slate-700'
            }`}
          >
            App
          </button>
          <button
            onClick={() => setLogFile('error')}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              logFile === 'error'
                ? 'bg-red-500/20 text-red-400'
                : 'text-slate-400 hover:bg-slate-700'
            }`}
          >
            Errors
          </button>
        </div>

        {/* Level filter */}
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="px-2 py-1 text-xs bg-slate-800 border border-slate-600 rounded-lg
                   text-slate-300 focus:border-cyan-500 outline-none"
        >
          <option value="">All levels</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>

        {/* Search */}
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search logs..."
          className="flex-1 max-w-xs px-3 py-1 text-xs bg-slate-800 border border-slate-600
                   rounded-lg text-white placeholder-slate-500 focus:border-cyan-500 outline-none"
        />

        {/* Auto-refresh toggle */}
        <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
            className="w-3 h-3 rounded border-slate-500 bg-slate-700
                     checked:bg-cyan-500 checked:border-cyan-500"
          />
          Auto-refresh
        </label>

        {/* Manual refresh */}
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="p-1.5 text-slate-400 hover:text-white rounded transition-colors"
          title="Refresh"
        >
          <svg
            className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>

        {/* Stats */}
        <span className="text-xs text-slate-500">
          {total} entries
        </span>
      </div>

      {/* Log entries */}
      <div ref={containerRef} className="flex-1 overflow-y-auto font-mono text-xs">
        {error ? (
          <div className="p-4 text-red-400">
            Error loading logs: {error}
          </div>
        ) : logs.length === 0 ? (
          <div className="p-4 text-slate-500 text-center">
            {loading ? 'Loading logs...' : 'No logs found'}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-slate-800 text-slate-400">
              <tr>
                <th className="px-2 py-1.5 text-left w-16">Time</th>
                <th className="px-2 py-1.5 text-left w-16">Level</th>
                <th className="px-2 py-1.5 text-left w-32">Event</th>
                <th className="px-2 py-1.5 text-left">Message / Data</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log, index) => {
                const isExpanded = expandedRows.has(index);
                const hasData = Object.keys(log.data).length > 0;

                return (
                  <tr
                    key={index}
                    onClick={() => hasData && toggleRowExpanded(index)}
                    className={`border-b border-slate-800 hover:bg-slate-800/50
                              ${hasData ? 'cursor-pointer' : ''}
                              ${isExpanded ? 'bg-slate-800/30' : ''}`}
                  >
                    <td className="px-2 py-1 text-slate-500 whitespace-nowrap align-top">
                      <span title={log.timestamp}>
                        {formatTimestamp(log.timestamp)}
                      </span>
                    </td>
                    <td className="px-2 py-1 align-top">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium
                                  ${LEVEL_COLORS[log.level] || 'text-slate-400'}
                                  ${LEVEL_BG[log.level] || 'bg-slate-500/20'}`}
                      >
                        {log.level}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-cyan-300 align-top truncate max-w-[8rem]">
                      {log.event}
                    </td>
                    <td className="px-2 py-1 text-slate-300 align-top">
                      <div className="flex items-start gap-2">
                        {hasData && (
                          <span className="text-slate-500 select-none">
                            {isExpanded ? '▼' : '▶'}
                          </span>
                        )}
                        <div className="flex-1 min-w-0">
                          {log.message && (
                            <div className="truncate">{log.message}</div>
                          )}
                          {isExpanded && hasData && (
                            <pre className="mt-2 p-2 bg-slate-900 rounded text-slate-400 overflow-x-auto">
                              {JSON.stringify(log.data, null, 2)}
                            </pre>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {hasMore && (
          <div className="p-2 text-center text-slate-500 text-xs">
            Showing first 200 entries. Use filters to narrow down.
          </div>
        )}
      </div>
    </div>
  );
}
