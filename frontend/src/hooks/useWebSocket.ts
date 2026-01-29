/**
 * WebSocket hook for real-time trace updates.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useTraceStore } from '@/stores/useTraceStore';

/**
 * Get the WebSocket URL based on environment or current location.
 * In production (when served by FastAPI), uses the current host.
 * In development, uses the configured WS_URL or localhost:8000.
 */
function getWebSocketUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_WS_URL;

  if (configuredUrl) {
    return configuredUrl;
  }

  // Construct WebSocket URL from current location
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }

  // Fallback for SSR
  return 'ws://localhost:8000';
}

interface WebSocketEvent {
  event_type: string;
  trace_id?: string;
  span_id?: string;
  data?: Record<string, unknown>;
  [key: string]: unknown;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();

  const {
    setConnectionStatus,
    addTrace,
    updateTrace,
    fetchTraces,
    fetchTraceDetail,
    selectedTraceId,
  } = useTraceStore();

  const handleEvent = useCallback(
    (event: WebSocketEvent) => {
      const data = event.data || {};
      switch (event.event_type) {
        case 'trace_started':
          addTrace({
            id: event.trace_id as string,
            input_prompt: (data.input_prompt as string) || '',
            status: 'running',
            started_at: (data.started_at as string) || new Date().toISOString(),
            total_tokens: 0,
            total_duration_ms: 0,
            spans: [],
            operational_summary: data.operational_summary as typeof data.operational_summary,
          });
          break;

        case 'trace_ended':
          updateTrace(event.trace_id as string, {
            status: data.error ? 'error' : 'completed',
            final_output: data.final_output as string,
            error: data.error as string,
            ended_at: (data.ended_at as string) || new Date().toISOString(),
            total_duration_ms: data.total_duration_ms as number,
            total_tokens: data.total_tokens as number,
            operational_summary: data.operational_summary as typeof data.operational_summary,
          });
          break;

        case 'span_started':
        case 'span_ended':
          // Refresh trace list
          fetchTraces();
          // Also refresh selected trace detail if it matches
          if (selectedTraceId && event.trace_id === selectedTraceId) {
            fetchTraceDetail(selectedTraceId);
          }
          break;

        default:
          console.log('Unknown event:', event.event_type);
      }
    },
    [addTrace, updateTrace, fetchTraces, fetchTraceDetail, selectedTraceId]
  );

  const connect = useCallback(() => {
    setConnectionStatus('connecting');

    const wsUrl = getWebSocketUrl();
    const ws = new WebSocket(`${wsUrl}/traces/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnectionStatus('connected');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnectionStatus('disconnected');
      // Reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnectionStatus('disconnected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketEvent;
        handleEvent(data);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };
  }, [setConnectionStatus, handleEvent]);

  useEffect(() => {
    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return wsRef.current;
}
