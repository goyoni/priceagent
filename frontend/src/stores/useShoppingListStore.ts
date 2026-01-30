/**
 * Zustand store for shopping list with localStorage persistence.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { ShoppingListItem, PriceSearchSession } from '@/lib/types';

interface ShoppingListState {
  // State
  items: ShoppingListItem[];
  isLoading: boolean;

  // Active price search session
  activeSearchSession: PriceSearchSession | null;

  // Actions
  addItem: (item: Omit<ShoppingListItem, 'id' | 'added_at'>) => ShoppingListItem;
  removeItem: (id: string) => void;
  updateItem: (id: string, updates: Partial<Omit<ShoppingListItem, 'id' | 'added_at'>>) => void;
  clearList: () => void;
  getItemById: (id: string) => ShoppingListItem | undefined;
  isDuplicate: (modelNumber: string) => boolean;

  // Price search actions (to be implemented in Commit 5)
  setActiveSearchSession: (session: PriceSearchSession | null) => void;
}

export const useShoppingListStore = create<ShoppingListState>()(
  persist(
    (set, get) => ({
      // Initial state
      items: [],
      isLoading: false,
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
    }),
    {
      name: 'priceagent_shopping_list',
      storage: createJSONStorage(() => localStorage),
      // Only persist items, not loading state or active session
      partialize: (state) => ({ items: state.items }),
    }
  )
);
