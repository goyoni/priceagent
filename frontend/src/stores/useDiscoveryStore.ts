/**
 * Zustand store for product discovery state.
 */

import { create } from 'zustand';
import { api } from '@/lib/api';
import type { DiscoveredProduct, DiscoverySearchSummary, DiscoveryResponse } from '@/lib/types';
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
  searchSummary: DiscoverySearchSummary | null;
  noResultsMessage: string | null;
  suggestions: string[];
  criteriaFeedback: string[];
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
  setSearchComplete: (response: DiscoveryResponse) => void;
  loadHistory: () => void;
  loadFromTrace: (traceId: string, query: string) => Promise<void>;
}

export const useDiscoveryStore = create<DiscoveryState>((set, get) => ({
  // Initial state
  query: '',
  isSearching: false,
  currentTraceId: null,
  products: [],
  searchSummary: null,
  noResultsMessage: null,
  suggestions: [],
  criteriaFeedback: [],
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
    searchSummary: null,
    noResultsMessage: null,
    suggestions: [],
    criteriaFeedback: [],
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
      searchSummary: null,
      noResultsMessage: null,
      suggestions: [],
      criteriaFeedback: [],
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
  setSearchComplete: (response: DiscoveryResponse) => {
    const { query, currentTraceId } = get();
    const products = response.products || [];

    // Add to history if we have products or if search was completed
    if (query) {
      const historyItem = addToDiscoveryHistory({
        query,
        timestamp: Date.now(),
        productCount: products.length,
        traceId: currentTraceId || undefined,
      });

      set((state) => ({
        products,
        searchSummary: response.search_summary || null,
        noResultsMessage: response.no_results_message || null,
        suggestions: response.suggestions || [],
        criteriaFeedback: response.criteria_feedback || [],
        isSearching: false,
        statusMessage: null,
        history: [historyItem, ...state.history.slice(0, 49)],
      }));
    } else {
      set({
        products,
        searchSummary: response.search_summary || null,
        noResultsMessage: response.no_results_message || null,
        suggestions: response.suggestions || [],
        criteriaFeedback: response.criteria_feedback || [],
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
      searchSummary: null,
      noResultsMessage: null,
      suggestions: [],
      criteriaFeedback: [],
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
      let discoveryResponse: DiscoveryResponse = { products: [] };
      if (data.output) {
        try {
          // Try to parse as discovery results
          const parsed = typeof data.output === 'string' ? JSON.parse(data.output) : data.output;
          if (parsed.products && Array.isArray(parsed.products)) {
            discoveryResponse = parsed;
          } else if (Array.isArray(parsed)) {
            discoveryResponse = { products: parsed };
          }
        } catch {
          console.log('[Discovery] Could not parse trace output as products');
        }
      }

      set({
        products: discoveryResponse.products,
        searchSummary: discoveryResponse.search_summary || null,
        noResultsMessage: discoveryResponse.no_results_message || null,
        suggestions: discoveryResponse.suggestions || [],
        criteriaFeedback: discoveryResponse.criteria_feedback || [],
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
