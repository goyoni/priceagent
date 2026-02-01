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
  originalTraceId: string | null;  // First trace ID in conversation (for linking child traces)
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
  originalTraceId: null,
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
    originalTraceId: null,
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
        originalTraceId: response.trace_id,  // Store as original trace for conversation
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
    const { products, country, messages, sessionId, originalTraceId } = get();
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
        sessionId,
        originalTraceId || undefined  // Link to original trace in conversation
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
    const { query, currentTraceId, originalTraceId } = get();
    const products = response.products || [];
    const isRefinement = originalTraceId && currentTraceId !== originalTraceId;

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

    // Add to history only for original searches (not refinements)
    if (query && !isRefinement) {
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
    // Generate new session for continuing the conversation
    const newSessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

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
      originalTraceId: traceId,  // Set original trace for conversation linking
      statusMessage: 'Loading previous results...',
      messages: [],
      sessionId: newSessionId,
    });

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';

      // Fetch traces list to get parent with nested children
      const listResponse = await fetch(`${apiUrl}/traces/`);
      if (!listResponse.ok) {
        throw new Error('Failed to load traces');
      }
      const listData = await listResponse.json();
      const parentTrace = listData.traces?.find((t: { id: string }) => t.id === traceId);

      // Also fetch the trace detail for full output
      const response = await fetch(`${apiUrl}/traces/${traceId}`);
      if (!response.ok) {
        throw new Error('Failed to load trace');
      }

      const data = await response.json();
      console.log('[Discovery] Loaded trace:', traceId, 'status:', data.status, 'has final_output:', !!data.final_output);

      // Helper to parse discovery response from output
      const parseOutput = (outputText: string): DiscoveryResponse => {
        if (!outputText) return { products: [] };
        try {
          const parsed = typeof outputText === 'string' ? JSON.parse(outputText) : outputText;
          if (parsed.products && Array.isArray(parsed.products)) {
            return parsed;
          } else if (Array.isArray(parsed)) {
            return { products: parsed };
          }
        } catch {
          console.log('[Discovery] Could not parse trace output as products');
        }
        return { products: [] };
      };

      // Helper to extract user query from child trace input_prompt
      const extractUserQuery = (inputPrompt: string): string => {
        // Child traces have format "...User's refinement request: <query>\nUser country: ..."
        const refinementMatch = inputPrompt.match(/User's refinement request:\s*(.+?)(?:\n|$)/);
        if (refinementMatch) {
          return refinementMatch[1].trim();
        }
        // Fallback: try "New user message:" format
        const newMsgMatch = inputPrompt.match(/New user message:\s*(.+)/s);
        if (newMsgMatch) {
          return newMsgMatch[1].trim();
        }
        // Fallback: just return the whole prompt
        return inputPrompt;
      };

      // Parse parent trace output
      const outputText = data.final_output || data.output || '';
      const discoveryResponse = parseOutput(outputText);
      console.log('[Discovery] Parsed', discoveryResponse.products.length, 'products from parent trace');

      // Build conversation messages starting with parent
      const messages: ConversationMessage[] = [];
      let baseTime = Date.now() - 10000;  // Start timestamps in past

      // Parent user message
      messages.push({
        id: `msg_${baseTime}_user`,
        role: 'user',
        content: query,
        timestamp: baseTime,
      });
      baseTime += 1000;

      // Parent assistant message
      messages.push({
        id: `msg_${baseTime}_assistant`,
        role: 'assistant',
        content: discoveryResponse.products.length > 0
          ? `Found ${discoveryResponse.products.length} product${discoveryResponse.products.length === 1 ? '' : 's'} matching your criteria.`
          : discoveryResponse.no_results_message || 'No products found.',
        timestamp: baseTime,
        traceId,
        productsSnapshot: discoveryResponse.products,
      });
      baseTime += 1000;

      // Track the latest products (from last refinement or parent)
      let latestProducts = discoveryResponse.products;
      let latestResponse = discoveryResponse;
      let latestTraceId = traceId;

      // Add child traces (refinements) if any
      const childTraces = parentTrace?.child_traces || [];
      if (childTraces.length > 0) {
        console.log('[Discovery] Loading', childTraces.length, 'child traces (refinements)');

        for (const child of childTraces) {
          // Fetch child trace detail for full output
          const childResponse = await fetch(`${apiUrl}/traces/${child.id}`);
          if (childResponse.ok) {
            const childData = await childResponse.json();
            const childOutput = parseOutput(childData.final_output || childData.output || '');

            // User refinement message
            const userQuery = extractUserQuery(child.input_prompt || '');
            messages.push({
              id: `msg_${baseTime}_user`,
              role: 'user',
              content: userQuery,
              timestamp: baseTime,
              productsSnapshot: latestProducts,  // Snapshot before this refinement
            });
            baseTime += 1000;

            // Assistant response
            messages.push({
              id: `msg_${baseTime}_assistant`,
              role: 'assistant',
              content: childOutput.products.length > 0
                ? `Found ${childOutput.products.length} product${childOutput.products.length === 1 ? '' : 's'} matching your criteria.`
                : childOutput.no_results_message || 'No products found.',
              timestamp: baseTime,
              traceId: child.id,
              productsSnapshot: childOutput.products,
            });
            baseTime += 1000;

            // Update latest
            if (childOutput.products.length > 0) {
              latestProducts = childOutput.products;
              latestResponse = childOutput;
              latestTraceId = child.id;
            }
          }
        }
      }

      set({
        products: latestProducts,
        searchSummary: latestResponse.search_summary || null,
        noResultsMessage: latestResponse.no_results_message || null,
        suggestions: latestResponse.suggestions || [],
        criteriaFeedback: latestResponse.criteria_feedback || [],
        isSearching: false,
        isLoadingFromHistory: false,
        statusMessage: null,
        messages,
        currentTraceId: latestTraceId,
      });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load';
      set({
        error: errorMessage,
        isSearching: false,
        isLoadingFromHistory: false,
        statusMessage: null,
        sessionId: null,  // Clear session on error
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
