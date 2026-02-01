/**
 * ProductDiscoveryView component for AI-powered product recommendations.
 * Allows users to describe what they need in natural language.
 * Supports conversational refinements.
 */

'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useDiscoveryStore } from '@/stores/useDiscoveryStore';
import { DiscoveryResultsTable } from './DiscoveryResultsTable';
import { CountrySelector } from '@/components/ui/CountrySelector';
import type { DiscoveredProduct, ShoppingListItem, DiscoveryResponse, ConversationMessage } from '@/lib/types';

interface ProductDiscoveryViewProps {
  onAddToShoppingList: (item: Omit<ShoppingListItem, 'id' | 'added_at'>) => void;
  country: string;
  onCountryChange?: (country: string) => void;
}

/**
 * Parse discovery response from agent output.
 */
function parseDiscoveryResponse(output: string): DiscoveryResponse {
  try {
    // Try to parse as JSON directly
    const parsed = JSON.parse(output);

    // Extract products array with proper typing
    const extractProducts = (items: unknown[]): DiscoveredProduct[] => {
      return items.map((p: unknown, index: number): DiscoveredProduct => {
        const item = p as Record<string, unknown>;
        return {
          id: String(item.id || `prod_${Date.now()}_${index}`),
          name: String(item.name || 'Unknown Product'),
          brand: item.brand ? String(item.brand) : undefined,
          model_number: item.model_number ? String(item.model_number) : undefined,
          category: String(item.category || 'product'),
          key_specs: Array.isArray(item.key_specs) ? item.key_specs.map(String) : [],
          price_range: item.price_range ? String(item.price_range) : undefined,
          why_recommended: String(item.why_recommended || ''),
          price: typeof item.price === 'number' ? item.price : undefined,
          currency: item.currency ? String(item.currency) : undefined,
          url: item.url ? String(item.url) : undefined,
          rating: typeof item.rating === 'number' ? item.rating : undefined,
        };
      });
    };

    if (parsed.products && Array.isArray(parsed.products)) {
      return {
        products: extractProducts(parsed.products),
        search_summary: parsed.search_summary,
        no_results_message: parsed.no_results_message,
        suggestions: parsed.suggestions,
        criteria_feedback: parsed.criteria_feedback,
      };
    }

    if (Array.isArray(parsed)) {
      return {
        products: extractProducts(parsed),
      };
    }

    console.log('[Discovery] Output is not a products array:', parsed);
    return { products: [] };
  } catch (e) {
    // Try to extract JSON from markdown or mixed content
    const jsonMatch = output.match(/\{[\s\S]*"products"[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        if (parsed.products && Array.isArray(parsed.products)) {
          return parseDiscoveryResponse(JSON.stringify(parsed));
        }
      } catch {
        console.log('[Discovery] Failed to extract JSON from output');
      }
    }

    console.log('[Discovery] Failed to parse output as JSON:', e);
    return { products: [] };
  }
}

export function ProductDiscoveryView({
  onAddToShoppingList,
  country,
  onCountryChange,
}: ProductDiscoveryViewProps) {
  const {
    query,
    setQuery,
    country: storeCountry,
    setCountry,
    isSearching,
    isLoadingFromHistory,
    currentTraceId,
    products,
    searchSummary,
    noResultsMessage,
    suggestions,
    criteriaFeedback,
    error,
    statusMessage,
    messages,
    sessionId,
    setStatusMessage,
    setError,
    runDiscovery,
    sendRefinement,
    setSearchComplete,
    clearResults,
    loadFromMessage,
  } = useDiscoveryStore();

  // Sync country from props to store
  useEffect(() => {
    if (country !== storeCountry) {
      setCountry(country);
    }
  }, [country, storeCountry, setCountry]);

  const [addingProductId, setAddingProductId] = useState<string | undefined>();
  const [localQuery, setLocalQuery] = useState(query);
  const [refinementInput, setRefinementInput] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const currentTraceIdRef = useRef<string | null>(null);

  // Keep ref in sync with current trace ID
  useEffect(() => {
    currentTraceIdRef.current = currentTraceId;
  }, [currentTraceId]);

  // Sync localQuery when store query changes (e.g., from loading history)
  useEffect(() => {
    if (query !== localQuery) {
      setLocalQuery(query);
    }
  }, [query]);

  // Example queries for suggestions
  const exampleQueries = [
    'Silent refrigerator for family of 4',
    'Energy efficient washing machine for small apartment',
    'Quiet dishwasher with good drying',
    'Large capacity oven for baking',
  ];

  // WebSocket listener for trace completion
  useEffect(() => {
    // Skip WebSocket when loading from history - we fetch directly instead
    if (!currentTraceId || !isSearching || isLoadingFromHistory) return;

    // Close any existing WebSocket before creating new one
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    const wsUrl = apiUrl.replace('http', 'ws') || 'ws://localhost:8000';
    const traceIdForThisEffect = currentTraceId;  // Capture for this effect instance

    console.log('[Discovery] Connecting WebSocket for trace:', traceIdForThisEffect);

    const ws = new WebSocket(`${wsUrl}/traces/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Discovery] WebSocket connected for trace:', traceIdForThisEffect);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Only process events for our trace - use ref to get current value
        // This prevents stale closure issues when a new search starts
        if (data.trace_id !== traceIdForThisEffect) {
          return;
        }

        // Also check if this is still the active trace
        if (currentTraceIdRef.current !== traceIdForThisEffect) {
          console.log('[Discovery] Ignoring message for old trace:', traceIdForThisEffect);
          ws.close();
          return;
        }

        // Update status message from span events
        if (data.event_type === 'span_started' && data.data?.name) {
          setStatusMessage(data.data.name);
        }

        // Handle trace completion
        if (data.event_type === 'trace_ended') {
          console.log('[Discovery] Trace completed:', traceIdForThisEffect);

          if (data.data?.error) {
            console.error('[Discovery] Trace error:', data.data.error);
            setError(data.data.error);
            setSearchComplete({ products: [] });
          } else {
            const finalOutput = data.data?.final_output || '';
            console.log('[Discovery] Final output length:', finalOutput.length);
            console.log('[Discovery] Final output preview:', finalOutput.substring(0, 500));

            const response = parseDiscoveryResponse(finalOutput);
            console.log('[Discovery] Parsed products:', response.products.length);

            if (response.products.length === 0 && finalOutput.length > 0) {
              console.log('[Discovery] No products parsed, full output:', finalOutput);
            }

            setSearchComplete(response);
          }

          ws.close();
        }
      } catch (err) {
        console.error('[Discovery] WebSocket message parse error:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('[Discovery] WebSocket error:', err);
    };

    ws.onclose = () => {
      console.log('[Discovery] WebSocket closed for trace:', traceIdForThisEffect);

      // Only fetch fallback if this is still the active trace and still searching
      if (currentTraceIdRef.current === traceIdForThisEffect) {
        // Use a small delay to check if still searching (state might have updated)
        setTimeout(() => {
          const store = useDiscoveryStore.getState();
          if (store.isSearching && store.currentTraceId === traceIdForThisEffect) {
            console.log('[Discovery] Fetching trace directly as fallback');
            fetch(`${apiUrl}/traces/${traceIdForThisEffect}`)
              .then((res) => res.json())
              .then((trace) => {
                if (trace.status === 'completed' && trace.final_output) {
                  const response = parseDiscoveryResponse(trace.final_output);
                  setSearchComplete(response);
                } else if (trace.status === 'error') {
                  setError(trace.error || 'Discovery failed');
                  setSearchComplete({ products: [] });
                }
              })
              .catch((err) => {
                console.error('[Discovery] Fallback fetch failed:', err);
              });
          }
        }, 100);
      }
    };

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [currentTraceId, isSearching, isLoadingFromHistory, setStatusMessage, setError, setSearchComplete]);

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localQuery.trim() || isSearching) return;

    try {
      await runDiscovery(localQuery, country);
    } catch (err) {
      console.error('[Discovery] Search failed:', err);
    }
  }, [localQuery, isSearching, runDiscovery, country]);

  const handleAddToList = useCallback((product: DiscoveredProduct) => {
    setAddingProductId(product.id);

    const item: Omit<ShoppingListItem, 'id' | 'added_at'> = {
      product_name: product.name,
      model_number: product.model_number,
      specs_summary: product.key_specs.slice(0, 3).join(', '),
      source: 'discovery',
    };

    onAddToShoppingList(item);

    // Brief visual feedback
    setTimeout(() => setAddingProductId(undefined), 500);
  }, [onAddToShoppingList]);

  const handleSuggestionClick = (suggestion: string) => {
    setLocalQuery(suggestion);
    setQuery(suggestion);
  };

  // Handle refinement submission
  const handleRefinementSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refinementInput.trim() || isSearching || !sessionId) return;

    try {
      await sendRefinement(refinementInput);
      setRefinementInput('');
    } catch (err) {
      console.error('[Discovery] Refinement failed:', err);
    }
  }, [refinementInput, isSearching, sessionId, sendRefinement]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (chatEndRef.current && messages.length > 0) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length]);

  return (
    <div className="space-y-6">
      {/* Discovery Form */}
      <div className="bg-white shadow-soft border border-gray-200 rounded-xl p-6">
        <h2 className="text-xl font-semibold text-gray-800 mb-2">
          What are you looking for?
        </h2>
        <p className="text-gray-500 text-sm mb-4">
          Describe your needs in natural language - our AI will find the best products for you.
        </p>

        <form onSubmit={handleSearch} className="space-y-4">
          <textarea
            value={localQuery}
            onChange={(e) => setLocalQuery(e.target.value)}
            placeholder="Example: I need a silent refrigerator for a family of 4 with an open kitchen layout"
            dir="auto"
            className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl
                     text-gray-800 placeholder-gray-400 outline-none resize-none
                     focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20
                     transition-all duration-300"
            rows={3}
            disabled={isSearching}
          />

          <div className="flex items-center justify-between">
            {onCountryChange ? (
              <CountrySelector
                value={country}
                onChange={onCountryChange}
                compact
              />
            ) : (
              <div className="text-xs text-gray-400">
                Country: {country}
              </div>
            )}
            <button
              type="submit"
              disabled={isSearching || !localQuery.trim()}
              className="px-6 py-2.5 bg-gradient-to-r from-indigo-500 to-blue-500
                       hover:from-indigo-400 hover:to-blue-400
                       disabled:from-gray-200 disabled:to-gray-200
                       text-white font-medium rounded-xl
                       transition-all duration-300 flex items-center gap-2"
            >
              {isSearching ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Discovering...
                </>
              ) : (
                <>
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                    />
                  </svg>
                  Discover Products
                </>
              )}
            </button>
          </div>
        </form>

        {/* Status message */}
        {isSearching && statusMessage && (
          <div className="mt-4 text-center text-gray-500 text-sm animate-pulse">
            {statusMessage}
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
            {error}
          </div>
        )}
      </div>

      {/* No results feedback (when search completed but no products found) */}
      {!isSearching && products.length === 0 && !error && (noResultsMessage || criteriaFeedback.length > 0 || searchSummary) && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-6 space-y-4">
          {/* No results message */}
          {noResultsMessage && (
            <div className="text-amber-400 font-medium">
              {noResultsMessage}
            </div>
          )}

          {/* Search summary - what was searched */}
          {searchSummary && (
            <div className="space-y-2">
              <h3 className="text-gray-600 text-sm font-medium">What we searched for:</h3>
              <div className="text-gray-500 text-sm">
                <span className="text-indigo-600">&ldquo;{searchSummary.original_requirement}&rdquo;</span>
                {searchSummary.category && (
                  <span className="ml-2 text-gray-400">({searchSummary.category})</span>
                )}
              </div>
              {searchSummary.search_attempts && searchSummary.search_attempts.length > 0 && (
                <div className="mt-2">
                  <span className="text-gray-400 text-xs">
                    Searched {searchSummary.search_attempts.length} queries across{' '}
                    {searchSummary.search_attempts.reduce((acc, a) => acc + (a.scrapers?.length || 0), 0)} sources
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Criteria that were used */}
          {criteriaFeedback.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-gray-600 text-sm font-medium">Search criteria used:</h3>
              <ul className="text-gray-500 text-sm space-y-1">
                {criteriaFeedback.map((criterion, idx) => (
                  <li key={idx} className="flex items-start">
                    <span className="text-indigo-600 mr-2">{criterion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggestions */}
          {suggestions.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-gray-600 text-sm font-medium">Suggestions:</h3>
              <ul className="text-gray-500 text-sm space-y-1">
                {suggestions.map((suggestion, idx) => (
                  <li key={idx} className="flex items-start">
                    <span className="text-amber-400 mr-2">&#8226;</span>
                    <span>{suggestion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Clear button */}
          <button
            onClick={clearResults}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            Clear and try again
          </button>
        </div>
      )}

      {/* Example suggestions (only when no search performed yet) */}
      {!isSearching && products.length === 0 && !error && !noResultsMessage && !searchSummary && criteriaFeedback.length === 0 && (
        <div className="text-center">
          <p className="text-gray-400 text-sm mb-3">Or try one of these examples:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {exampleQueries.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => handleSuggestionClick(suggestion)}
                className="px-3 py-1.5 text-sm text-gray-500 bg-white shadow-soft rounded-lg
                         hover:bg-gray-100 hover:text-gray-800 transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {products.length > 0 && (
        <div className="bg-white/30 border border-gray-200 rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="text-gray-500 text-sm">
              Found {products.length} recommended products
            </span>
            <button
              onClick={clearResults}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Clear results
            </button>
          </div>

          {/* Market notes / Filtering notes - show when criteria were adapted */}
          {searchSummary?.filtering_notes && (
            <div className="mb-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
              <div className="text-blue-400 text-sm">
                <span className="font-medium">Note:</span> {searchSummary.filtering_notes}
              </div>
            </div>
          )}

          {searchSummary?.market_notes && !searchSummary?.filtering_notes && (
            <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded-lg">
              <div className="text-gray-500 text-sm">
                <span className="font-medium">Market info:</span> {searchSummary.market_notes}
              </div>
            </div>
          )}

          <DiscoveryResultsTable
            products={products}
            onAddToList={handleAddToList}
            isAddingId={addingProductId}
          />

          {/* Conversation refinement section */}
          {sessionId && (
            <div className="mt-6 border-t border-gray-200 pt-6">
              <h3 className="text-sm font-medium text-gray-600 mb-3">
                Refine your search
              </h3>

              {/* Conversation history */}
              {messages.length > 1 && (
                <div className="mb-4 max-h-40 overflow-y-auto space-y-2 pr-2">
                  {messages.slice(1).map((msg) => {
                    const isAssistant = msg.role === 'assistant';
                    const isSelected = isAssistant && msg.traceId === currentTraceId;
                    const isClickable = isAssistant && msg.productsSnapshot && msg.productsSnapshot.length > 0;

                    return (
                      <div
                        key={msg.id}
                        onClick={() => {
                          if (isClickable) {
                            loadFromMessage(msg.id);
                          }
                        }}
                        className={`text-sm rounded-lg px-3 py-2 ${
                          msg.role === 'user'
                            ? 'bg-indigo-50 text-indigo-700 ml-8'
                            : `mr-8 ${isSelected
                                ? 'bg-indigo-100 text-indigo-700 border border-indigo-300'
                                : 'bg-gray-50 text-gray-600'
                              } ${isClickable ? 'cursor-pointer hover:bg-gray-100' : ''}`
                        }`}
                        title={isClickable ? 'Click to view these results' : undefined}
                      >
                        <span className="font-medium">
                          {msg.role === 'user' ? 'You' : 'AI'}:
                        </span>{' '}
                        {msg.content}
                        {isClickable && (
                          <span className="ml-1 text-xs text-gray-400">
                            (click to view)
                          </span>
                        )}
                      </div>
                    );
                  })}
                  <div ref={chatEndRef} />
                </div>
              )}

              {/* Refinement input */}
              <form onSubmit={handleRefinementSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={refinementInput}
                  onChange={(e) => setRefinementInput(e.target.value)}
                  placeholder="e.g., 'show cheaper options' or 'prefer Samsung'"
                  dir="auto"
                  className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg
                           text-gray-800 placeholder-gray-400 text-sm outline-none
                           focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/20
                           transition-all duration-300"
                  disabled={isSearching}
                />
                <button
                  type="submit"
                  disabled={isSearching || !refinementInput.trim()}
                  className="px-4 py-2 bg-gradient-to-r from-indigo-500 to-blue-500
                           hover:from-indigo-400 hover:to-blue-400
                           disabled:from-gray-200 disabled:to-gray-200
                           text-white text-sm font-medium rounded-lg
                           transition-all duration-300 flex items-center gap-1"
                >
                  {isSearching ? (
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                        fill="none"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  )}
                  Refine
                </button>
              </form>

              {/* Quick refinement suggestions */}
              <div className="mt-2 flex flex-wrap gap-2">
                {['cheaper options', 'quieter models', 'larger capacity', 'different brands'].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setRefinementInput(suggestion)}
                    disabled={isSearching}
                    className="text-xs text-gray-500 bg-white hover:bg-gray-100
                             px-2 py-1 rounded transition-colors disabled:opacity-50"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
