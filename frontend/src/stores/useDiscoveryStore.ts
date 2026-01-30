/**
 * Zustand store for product discovery state.
 */

import { create } from 'zustand';
import { api } from '@/lib/api';
import type { DiscoveredProduct } from '@/lib/types';

interface DiscoveryState {
  // State
  query: string;
  isSearching: boolean;
  currentTraceId: string | null;
  products: DiscoveredProduct[];
  error: string | null;
  statusMessage: string | null;

  // Actions
  setQuery: (query: string) => void;
  setProducts: (products: DiscoveredProduct[]) => void;
  setError: (error: string | null) => void;
  setStatusMessage: (message: string | null) => void;
  clearResults: () => void;
  runDiscovery: (query: string) => Promise<string>;
  setSearchComplete: (products: DiscoveredProduct[]) => void;
}

export const useDiscoveryStore = create<DiscoveryState>((set, get) => ({
  // Initial state
  query: '',
  isSearching: false,
  currentTraceId: null,
  products: [],
  error: null,
  statusMessage: null,

  // Sync actions
  setQuery: (query) => set({ query }),
  setProducts: (products) => set({ products }),
  setError: (error) => set({ error }),
  setStatusMessage: (message) => set({ statusMessage: message }),

  clearResults: () => set({
    products: [],
    error: null,
    statusMessage: null,
    currentTraceId: null,
  }),

  // Start a discovery search
  runDiscovery: async (query) => {
    set({
      isSearching: true,
      error: null,
      products: [],
      query,
      statusMessage: 'Starting product discovery...',
    });

    try {
      const response = await api.runDiscovery(query);
      set({
        currentTraceId: response.trace_id,
        statusMessage: 'Researching products...',
      });
      return response.trace_id;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Discovery failed';
      set({
        error: errorMessage,
        isSearching: false,
        statusMessage: null,
      });
      throw err;
    }
  },

  // Called when WebSocket receives results
  setSearchComplete: (products) => set({
    products,
    isSearching: false,
    statusMessage: null,
  }),
}));
