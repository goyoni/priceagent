/**
 * Zustand store for search state management.
 */

import { create } from 'zustand';
import type { SearchResult, BundleResult } from '@/lib/types';
import { api } from '@/lib/api';

interface SearchState {
  // State
  query: string;
  isSearching: boolean;
  currentTraceId: string | null;
  results: SearchResult[];
  bundles: BundleResult[];
  selectedSellers: Array<{
    id: string;  // Unique identifier (seller_name + phone_number)
    seller_name: string;
    phone_number: string;
    product_name: string;
    listed_price: number;
  }>;
  error: string | null;

  // Actions
  setQuery: (query: string) => void;
  setResults: (results: SearchResult[]) => void;
  setBundles: (bundles: BundleResult[]) => void;
  toggleSellerSelection: (seller: Omit<SearchState['selectedSellers'][0], 'id'>) => void;
  isSellerSelected: (sellerName: string, phoneNumber: string) => boolean;
  clearSelection: () => void;
  setError: (error: string | null) => void;

  // Async actions
  runSearch: (query: string) => Promise<void>;
}

export const useSearchStore = create<SearchState>((set, get) => ({
  // Initial state
  query: '',
  isSearching: false,
  currentTraceId: null,
  results: [],
  bundles: [],
  selectedSellers: [],
  error: null,

  // Sync actions
  setQuery: (query) => set({ query }),

  setResults: (results) => set({ results }),

  setBundles: (bundles) => set({ bundles }),

  toggleSellerSelection: (seller) =>
    set((state) => {
      // Create unique ID from seller name + phone number
      const id = `${seller.seller_name}:${seller.phone_number}`;
      const exists = state.selectedSellers.some((s) => s.id === id);

      if (exists) {
        return {
          selectedSellers: state.selectedSellers.filter((s) => s.id !== id),
        };
      } else {
        return {
          selectedSellers: [...state.selectedSellers, { ...seller, id }],
        };
      }
    }),

  isSellerSelected: (sellerName, phoneNumber) => {
    const id = `${sellerName}:${phoneNumber}`;
    return get().selectedSellers.some((s) => s.id === id);
  },

  clearSelection: () => set({ selectedSellers: [] }),

  setError: (error) => set({ error }),

  // Async actions
  runSearch: async (query) => {
    set({ isSearching: true, error: null, query });
    try {
      const response = await api.runQuery(query, 'research');
      set({
        currentTraceId: response.trace_id,
        isSearching: false,
      });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Search failed',
        isSearching: false,
      });
    }
  },
}));
