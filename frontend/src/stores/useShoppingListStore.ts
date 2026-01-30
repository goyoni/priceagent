/**
 * Zustand store for shopping list with localStorage persistence.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { api } from '@/lib/api';
import type { ShoppingListItem, PriceSearchSession } from '@/lib/types';

const STORAGE_KEY = 'shoppingagent_shopping_list';
const OLD_STORAGE_KEY = 'priceagent_shopping_list';

/**
 * Migrate data from old storage key to new one (one-time migration).
 */
function migrateFromOldKey(): void {
  if (typeof window === 'undefined') return;

  try {
    const oldData = localStorage.getItem(OLD_STORAGE_KEY);
    const newData = localStorage.getItem(STORAGE_KEY);

    // Only migrate if old data exists and new data doesn't
    if (oldData && !newData) {
      console.log('[ShoppingList] Migrating from old storage key');
      localStorage.setItem(STORAGE_KEY, oldData);
      localStorage.removeItem(OLD_STORAGE_KEY);
    }
  } catch (error) {
    console.error('[ShoppingList] Migration failed:', error);
  }
}

// Run migration before store is created
migrateFromOldKey();

interface ShoppingListState {
  // State
  items: ShoppingListItem[];
  isLoading: boolean;
  isSearching: boolean;

  // Active price search session
  activeSearchSession: PriceSearchSession | null;

  // Actions
  addItem: (item: Omit<ShoppingListItem, 'id' | 'added_at'>) => ShoppingListItem;
  removeItem: (id: string) => void;
  updateItem: (id: string, updates: Partial<Omit<ShoppingListItem, 'id' | 'added_at'>>) => void;
  clearList: () => void;
  getItemById: (id: string) => ShoppingListItem | undefined;
  isDuplicate: (modelNumber: string) => boolean;

  // Price search actions
  setActiveSearchSession: (session: PriceSearchSession | null) => void;
  startPriceSearch: (country: string) => Promise<{ sessionId: string; traceId: string }>;
  markSearchComplete: (status: 'completed' | 'failed', error?: string) => void;
}

export const useShoppingListStore = create<ShoppingListState>()(
  persist(
    (set, get) => ({
      // Initial state
      items: [],
      isLoading: false,
      isSearching: false,
      activeSearchSession: null,

      // Add a new item
      addItem: (itemData) => {
        const newItem: ShoppingListItem = {
          ...itemData,
          id: `item_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
          added_at: new Date().toISOString(),
        };

        set((state) => ({
          items: [newItem, ...state.items],
        }));

        return newItem;
      },

      // Remove an item
      removeItem: (id) => {
        set((state) => ({
          items: state.items.filter((item) => item.id !== id),
        }));
      },

      // Update an item
      updateItem: (id, updates) => {
        set((state) => ({
          items: state.items.map((item) =>
            item.id === id ? { ...item, ...updates } : item
          ),
        }));
      },

      // Clear all items
      clearList: () => {
        set({ items: [] });
      },

      // Get item by ID
      getItemById: (id) => {
        return get().items.find((item) => item.id === id);
      },

      // Check for duplicate by model number
      isDuplicate: (modelNumber) => {
        if (!modelNumber) return false;
        return get().items.some(
          (item) => item.model_number?.toLowerCase() === modelNumber.toLowerCase()
        );
      },

      // Set active price search session
      setActiveSearchSession: (session) => {
        set({ activeSearchSession: session });
      },

      // Start a price search for all items
      startPriceSearch: async (country) => {
        const { items } = get();

        if (items.length === 0) {
          throw new Error('No items to search');
        }

        set({ isSearching: true });

        try {
          const searchItems = items.map((item) => ({
            product_name: item.product_name,
            model_number: item.model_number,
          }));

          const response = await api.startPriceSearch(searchItems, country);

          const session: PriceSearchSession = {
            id: response.session_id,
            trace_id: response.trace_id,
            status: 'running',
            country,
            started_at: new Date().toISOString(),
          };

          set({ activeSearchSession: session });

          return {
            sessionId: response.session_id,
            traceId: response.trace_id,
          };
        } catch (error) {
          set({ isSearching: false });
          throw error;
        }
      },

      // Mark search as complete
      markSearchComplete: (status, error) => {
        set((state) => ({
          isSearching: false,
          activeSearchSession: state.activeSearchSession
            ? {
                ...state.activeSearchSession,
                status,
                completed_at: new Date().toISOString(),
                error,
              }
            : null,
        }));
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      // Only persist items, not loading state or active session
      partialize: (state) => ({ items: state.items }),
    }
  )
);
