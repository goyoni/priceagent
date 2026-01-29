/**
 * Zustand store for trace state management.
 */

import { create } from 'zustand';
import type { Trace, ConnectionStatus } from '@/lib/types';
import { api } from '@/lib/api';

interface TraceState {
  // State
  traces: Trace[];
  selectedTraceId: string | null;
  selectedTrace: Trace | null;
  connectionStatus: ConnectionStatus;
  isLoading: boolean;
  error: string | null;

  // Actions
  setTraces: (traces: Trace[]) => void;
  selectTrace: (traceId: string | null) => void;
  setSelectedTraceDetail: (trace: Trace | null) => void;
  updateTrace: (traceId: string, updates: Partial<Trace>) => void;
  addTrace: (trace: Trace) => void;
  deleteTrace: (traceId: string) => Promise<void>;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Async actions
  fetchTraces: () => Promise<void>;
  fetchTraceDetail: (traceId: string) => Promise<void>;
}

export const useTraceStore = create<TraceState>((set, get) => ({
  // Initial state
  traces: [],
  selectedTraceId: null,
  selectedTrace: null,
  connectionStatus: 'connecting',
  isLoading: false,
  error: null,

  // Sync actions
  setTraces: (traces) => set({ traces: traces || [] }),

  selectTrace: (traceId) => {
    set({ selectedTraceId: traceId });
    if (traceId) {
      get().fetchTraceDetail(traceId);
    } else {
      set({ selectedTrace: null });
    }
  },

  setSelectedTraceDetail: (trace) => set({ selectedTrace: trace }),

  updateTrace: (traceId, updates) =>
    set((state) => ({
      traces: (state.traces || []).map((t) =>
        t.id === traceId ? { ...t, ...updates } : t
      ),
      selectedTrace:
        state.selectedTrace?.id === traceId
          ? { ...state.selectedTrace, ...updates }
          : state.selectedTrace,
    })),

  addTrace: (trace) =>
    set((state) => ({
      traces: [trace, ...(state.traces || [])].slice(0, 50),
    })),

  deleteTrace: async (traceId) => {
    try {
      await api.deleteTrace(traceId);
      set((state) => ({
        traces: (state.traces || []).filter((t) => t.id !== traceId),
        selectedTraceId: state.selectedTraceId === traceId ? null : state.selectedTraceId,
        selectedTrace: state.selectedTrace?.id === traceId ? null : state.selectedTrace,
      }));
    } catch (err) {
      console.error('Failed to delete trace:', err);
    }
  },

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  // Async actions
  fetchTraces: async () => {
    set({ isLoading: true, error: null });
    try {
      const traces = await api.getTraces();
      set({ traces: traces || [], isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch traces',
        isLoading: false,
      });
    }
  },

  fetchTraceDetail: async (traceId) => {
    set({ isLoading: true, error: null });
    try {
      const trace = await api.getTrace(traceId);
      set({ selectedTrace: trace, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to fetch trace',
        isLoading: false,
      });
    }
  },
}));
