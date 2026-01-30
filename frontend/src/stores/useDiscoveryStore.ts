/**
 * Zustand store for product discovery state.
 */

import { create } from 'zustand';
import { api } from '@/lib/api';
import type { DiscoveredProduct } from '@/lib/types';
import {
  DiscoveryHistoryItem,
  getDiscoveryHistory,
  addToDiscoveryHistory,
} from '@/lib/discoveryHistory';

interface DiscoveryState {
  // State
  query: string;
  isSearching: boolean;
  currentTraceId: string | null;
  products: DiscoveredProduct[];
  error: string | null;
  statusMessage: string | null;
  history: DiscoveryHistoryItem[];

  // Actions
  setQuery: (query: string) => void;
  setProducts: (products: DiscoveredProduct[]) => void;
  setError: (error: string | null) => void;
  setStatusMessage: (message: string | null) => void;
  clearResults: () => void;
  runDiscovery: (query: string) => Promise<string>;
  setSearchComplete: (products: DiscoveredProduct[]) => void;
  loadHistory: () => void;
  loadFromTrace: (traceId: string, query: string) => Promise<void>;
}

export const useDiscoveryStore = create<DiscoveryState>((set, get) => ({
  // Initial state
  query: '',
  isSearching: false,
  currentTraceId: null,
  products: [],
  error: null,
  statusMessage: null,
  history: [],

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

  // Load history from localStorage
  loadHistory: () => {
    const history = getDiscoveryHistory();
    set({ history });
  },

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
  setSearchComplete: (products) => {
    const { query, currentTraceId } = get();

    // Add to history if we have products
    if (products.length > 0 && query) {
      const historyItem = addToDiscoveryHistory({
        query,
        timestamp: Date.now(),
        productCount: products.length,
        traceId: currentTraceId || undefined,
      });

      set((state) => ({
        products,
        isSearching: false,
        statusMessage: null,
        history: [historyItem, ...state.history.slice(0, 49)],
      }));
    } else {
      set({
        products,
        isSearching: false,
        statusMessage: null,
      });
    }
  },

  // Load discovery results from a past trace
  loadFromTrace: async (traceId: string, query: string) => {
    set({
      isSearching: true,
      error: null,
      products: [],
      query,
      currentTraceId: traceId,
      statusMessage: 'Loading previous results...',
    });

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const response = await fetch(`${apiUrl}/traces/${traceId}`);

      if (!response.ok) {
        throw new Error('Failed to load trace');
      }

      const data = await response.json();

      // Parse discovery products from trace output
      let products: DiscoveredProduct[] = [];
      if (data.output) {
        try {
          // Try to parse as discovery results
          const parsed = typeof data.output === 'string' ? JSON.parse(data.output) : data.output;
          if (parsed.products && Array.isArray(parsed.products)) {
            products = parsed.products;
          } else if (Array.isArray(parsed)) {
            products = parsed;
          }
        } catch {
          console.log('[Discovery] Could not parse trace output as products');
        }
      }

      set({
        products,
        isSearching: false,
        statusMessage: null,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load';
      set({
        error: errorMessage,
        isSearching: false,
        statusMessage: null,
      });
    }
  },
}));
