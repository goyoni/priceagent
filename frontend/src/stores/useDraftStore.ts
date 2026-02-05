/**
 * Zustand store for draft message state management.
 */

import { create } from 'zustand';
import type { DraftMessage } from '@/lib/types';
import { api } from '@/lib/api';
import { generateWhatsAppLink } from '@/lib/utils';

interface DraftState {
  // State
  isModalOpen: boolean;
  isGenerating: boolean;
  drafts: DraftMessage[];
  sentIndices: Set<number>;
  error: string | null;

  // Actions
  openModal: () => void;
  closeModal: () => void;
  updateDraftMessage: (index: number, message: string) => void;
  updateDraftPhone: (index: number, phone: string) => void;
  markAsSent: (index: number) => void;
  clearDrafts: () => void;

  // Async actions
  generateDrafts: (
    sellers: Array<{
      seller_name: string;
      phone_number: string;
      products?: string[];  // List of products (preferred)
      product_name?: string;  // Legacy single product
      listed_price?: number;
    }>,
    country?: string  // Country for language detection (IL -> Hebrew)
  ) => Promise<void>;
}

export const useDraftStore = create<DraftState>((set, get) => ({
  // Initial state
  isModalOpen: false,
  isGenerating: false,
  drafts: [],
  sentIndices: new Set(),
  error: null,

  // Sync actions
  openModal: () => set({ isModalOpen: true }),

  closeModal: () =>
    set({
      isModalOpen: false,
      drafts: [],
      sentIndices: new Set(),
      error: null,
    }),

  updateDraftMessage: (index, message) =>
    set((state) => {
      const newDrafts = [...state.drafts];
      if (newDrafts[index]) {
        newDrafts[index] = {
          ...newDrafts[index],
          message,
          wa_link: generateWhatsAppLink(newDrafts[index].phone_number, message),
        };
      }
      return { drafts: newDrafts };
    }),

  updateDraftPhone: (index, phone) =>
    set((state) => {
      const newDrafts = [...state.drafts];
      if (newDrafts[index]) {
        newDrafts[index] = {
          ...newDrafts[index],
          phone_number: phone,
          wa_link: generateWhatsAppLink(phone, newDrafts[index].message),
        };
      }
      return { drafts: newDrafts };
    }),

  markAsSent: (index) =>
    set((state) => ({
      sentIndices: new Set([...state.sentIndices, index]),
    })),

  clearDrafts: () =>
    set({
      drafts: [],
      sentIndices: new Set(),
      error: null,
    }),

  // Async actions
  generateDrafts: async (sellers, country = 'IL') => {
    set({ isGenerating: true, error: null });
    try {
      const response = await api.generateDrafts({
        sellers,
        country,
      });
      set({
        drafts: response.drafts,
        isGenerating: false,
        isModalOpen: true,
      });
    } catch (err) {
      set({
        error:
          err instanceof Error ? err.message : 'Failed to generate drafts',
        isGenerating: false,
      });
    }
  },
}));
