/**
 * Zustand store for product discovery state.
 */

import { create } from 'zustand';
import { api } from '@/lib/api';
import type { DiscoveredProduct, DiscoverySearchSummary, DiscoveryResponse, ConversationMessage } from '@/lib/types';
import {
  DiscoveryHistoryItem,
  getDiscoveryHistory,
  addToDiscoveryHistory,
  deleteFromDiscoveryHistory,
} from '@/lib/discoveryHistory';

interface DiscoveryState {
  // State
  query: string;
  country: string;
  isSearching: boolean;
  isLoadingFromHistory: boolean;  // Flag to prevent WebSocket connection when loading past results
  currentTraceId: string | null;
  products: DiscoveredProduct[];
  searchSummary: DiscoverySearchSummary | null;
  noResultsMessage: string | null;
  suggestions: string[];
  criteriaFeedback: string[];
  error: string | null;
  statusMessage: string | null;
  history: DiscoveryHistoryItem[];

  // Conversation state
  messages: ConversationMessage[];
  sessionId: string | null;

  // Actions
  setQuery: (query: string) => void;
  setCountry: (country: string) => void;
  setProducts: (products: DiscoveredProduct[]) => void;
  setError: (error: string | null) => void;
  setStatusMessage: (message: string | null) => void;
  clearResults: () => void;
  runDiscovery: (query: string, country?: string) => Promise<string>;
  sendRefinement: (message: string) => Promise<string>;
  setSearchComplete: (response: DiscoveryResponse) => void;
  loadHistory: () => void;
  loadFromTrace: (traceId: string, query: string) => Promise<void>;
  loadFromMessage: (messageId: string) => void;
  deleteFromHistory: (id: string) => void;
  clearConversation: () => void;
}

export const useDiscoveryStore = create<DiscoveryState>((set, get) => ({
  // Initial state
  query: '',
  country: 'IL',
  isSearching: false,
  isLoadingFromHistory: false,
  currentTraceId: null,
  products: [],
  searchSummary: null,
  noResultsMessage: null,
  suggestions: [],
  criteriaFeedback: [],
  error: null,
  statusMessage: null,
  history: [],

  // Conversation state
  messages: [],
  sessionId: null,

  // Sync actions
  setQuery: (query) => set({ query }),
  setCountry: (country) => set({ country }),
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
    messages: [],
    sessionId: null,
  }),

  // Clear just the conversation (keep products)
  clearConversation: () => set({
    messages: [],
    sessionId: null,
  }),

  // Load history from localStorage
  loadHistory: () => {
    const history = getDiscoveryHistory();
    set({ history });
  },

  // Start a discovery search
  runDiscovery: async (query, country) => {
    const effectiveCountry = country || get().country;
    const newSessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    const userMessage: ConversationMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: Date.now(),
    };

    set({
      isSearching: true,
      error: null,
      products: [],
      searchSummary: null,
      noResultsMessage: null,
      suggestions: [],
      criteriaFeedback: [],
      query,
      country: effectiveCountry,
      statusMessage: 'Starting product discovery...',
      messages: [userMessage],
      sessionId: newSessionId,
    });

    try {
      const response = await api.runDiscovery(query, effectiveCountry);
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

  // Send a refinement message in the current conversation
  sendRefinement: async (message: string) => {
    const { products, country, messages, sessionId } = get();
    if (!sessionId) {
      throw new Error('No active session');
    }

    const userMessage: ConversationMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: Date.now(),
      productsSnapshot: products,  // Capture current products
    };

    set((state) => ({
      isSearching: true,
      error: null,
      statusMessage: 'Refining search...',
      messages: [...state.messages, userMessage],
    }));

    try {
      // Build conversation history for the API
      const conversationHistory = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      conversationHistory.push({ role: 'user', content: message });

      const response = await api.runDiscoveryRefinement(
        message,
        country,
        conversationHistory,
        sessionId
      );

      set({
        currentTraceId: response.trace_id,
        statusMessage: 'Updating recommendations...',
      });

      return response.trace_id;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Refinement failed';
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

    // Create assistant message for the conversation
    const assistantContent = products.length > 0
      ? `Found ${products.length} product${products.length === 1 ? '' : 's'} matching your criteria.`
      : response.no_results_message || 'No products found matching your criteria.';

    const assistantMessage: ConversationMessage = {
      id: `msg_${Date.now()}`,
      role: 'assistant',
      content: assistantContent,
      timestamp: Date.now(),
      traceId: currentTraceId || undefined,  // Associate trace ID with this message
      productsSnapshot: products,
    };

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
        messages: [...state.messages, assistantMessage],
      }));
    } else {
      set((state) => ({
        products,
        searchSummary: response.search_summary || null,
        noResultsMessage: response.no_results_message || null,
        suggestions: response.suggestions || [],
        criteriaFeedback: response.criteria_feedback || [],
        isSearching: false,
        statusMessage: null,
        messages: [...state.messages, assistantMessage],
      }));
    }
  },

  // Load discovery results from a past trace
  loadFromTrace: async (traceId: string, query: string) => {
    set({
      isSearching: true,
      isLoadingFromHistory: true,  // Flag to prevent WebSocket from connecting
      error: null,
      products: [],
      searchSummary: null,
      noResultsMessage: null,
      suggestions: [],
      criteriaFeedback: [],
      query,
      currentTraceId: traceId,
      statusMessage: 'Loading previous results...',
      messages: [],
      sessionId: null,
    });

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const response = await fetch(`${apiUrl}/traces/${traceId}`);

      if (!response.ok) {
        throw new Error('Failed to load trace');
      }

      const data = await response.json();
      console.log('[Discovery] Loaded trace:', traceId, 'status:', data.status, 'has final_output:', !!data.final_output);

      // Parse discovery products from trace output (API returns final_output, not output)
      let discoveryResponse: DiscoveryResponse = { products: [] };
      const outputText = data.final_output || data.output || '';

      if (outputText) {
        try {
          // Try to parse as discovery results
          const parsed = typeof outputText === 'string' ? JSON.parse(outputText) : outputText;
          if (parsed.products && Array.isArray(parsed.products)) {
            discoveryResponse = parsed;
          } else if (Array.isArray(parsed)) {
            discoveryResponse = { products: parsed };
          }
        } catch {
          console.log('[Discovery] Could not parse trace output as products');
        }
      }

      console.log('[Discovery] Parsed', discoveryResponse.products.length, 'products from trace');

      set({
        products: discoveryResponse.products,
        searchSummary: discoveryResponse.search_summary || null,
        noResultsMessage: discoveryResponse.no_results_message || null,
        suggestions: discoveryResponse.suggestions || [],
        criteriaFeedback: discoveryResponse.criteria_feedback || [],
        isSearching: false,
        isLoadingFromHistory: false,
        statusMessage: null,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load';
      set({
        error: errorMessage,
        isSearching: false,
        isLoadingFromHistory: false,
        statusMessage: null,
      });
    }
  },

  // Delete a discovery from history
  deleteFromHistory: (id: string) => {
    deleteFromDiscoveryHistory(id);
    set((state) => ({
      history: state.history.filter((item) => item.id !== id),
    }));
  },

  // Load products from a specific message in the conversation
  loadFromMessage: (messageId: string) => {
    const { messages } = get();
    const message = messages.find((m) => m.id === messageId);

    if (message && message.productsSnapshot) {
      set({
        products: message.productsSnapshot,
        currentTraceId: message.traceId || null,
      });
    }
  },
}));
