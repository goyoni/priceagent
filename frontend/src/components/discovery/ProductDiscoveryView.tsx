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
    // For WebSocket, use window.location if apiUrl is relative/empty
    const wsUrl = apiUrl
      ? apiUrl.replace('http', 'ws')
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
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

          {/* Search criteria used - always show when available */}
          {searchSummary?.criteria_used && searchSummary.criteria_used.length > 0 && (
            <div className="mb-4 p-3 bg-indigo-50 border border-indigo-200 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <span className="text-indigo-700 text-sm font-medium">
                  Search criteria ({searchSummary.criteria_used.length}):
                </span>
                <span className="text-gray-500 text-xs">
                  {searchSummary.category && `Category: ${searchSummary.category}`}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {searchSummary.criteria_used.slice(0, 8).map((criterion, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-1 text-xs rounded-full bg-white border border-indigo-200 text-gray-700"
                    title={criterion.explanation || criterion.market_context || undefined}
                  >
                    <span className="font-medium text-indigo-600 mr-1">{criterion.attribute}:</span>
                    <span>
                      {criterion.market_value || criterion.value || criterion.ideal_value || 'any'}
                    </span>
                    {criterion.source === 'user' && (
                      <span className="ml-1 text-indigo-400 text-[10px]">(you)</span>
                    )}
                  </span>
                ))}
                {searchSummary.criteria_used.length > 8 && (
                  <span className="text-xs text-gray-400 self-center">
                    +{searchSummary.criteria_used.length - 8} more
                  </span>
                )}
              </div>
            </div>
          )}

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

          {/* Conversation refinement section - WhatsApp style */}
          {sessionId && (
            <div className="mt-6 border-t border-gray-200 pt-4">
              {/* Chat container */}
              <div className="bg-gradient-to-b from-gray-50 to-gray-100 rounded-xl border border-gray-200 overflow-hidden">
                {/* Chat header */}
                <div className="bg-indigo-600 px-4 py-2 flex items-center gap-2">
                  <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center">
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <div>
                    <div className="text-white text-sm font-medium">Refine your search</div>
                    <div className="text-white/70 text-xs">
                      {isSearching ? 'Searching...' : 'Online'}
                    </div>
                  </div>
                </div>

                {/* Messages area */}
                <div className="p-4 max-h-64 overflow-y-auto space-y-3" style={{ minHeight: messages.length > 1 ? '120px' : '60px' }}>
                  {messages.length <= 1 ? (
                    <div className="text-center text-gray-400 text-sm py-2">
                      Ask me to refine your results...
                    </div>
                  ) : (
                    messages.slice(1).map((msg) => {
                      const isUser = msg.role === 'user';
                      const isAssistant = msg.role === 'assistant';
                      const isSelected = isAssistant && msg.traceId === currentTraceId;
                      const isClickable = isAssistant && msg.productsSnapshot && msg.productsSnapshot.length > 0;

                      return (
                        <div
                          key={msg.id}
                          className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                        >
                          <div
                            onClick={() => {
                              if (isClickable) {
                                loadFromMessage(msg.id);
                              }
                            }}
                            className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm relative
                              ${isUser
                                ? 'bg-indigo-500 text-white rounded-br-md'
                                : `${isSelected
                                    ? 'bg-white border-2 border-indigo-400 text-gray-800'
                                    : 'bg-white text-gray-700 border border-gray-200'
                                  } rounded-bl-md shadow-sm ${isClickable ? 'cursor-pointer hover:border-indigo-300' : ''}`
                              }`}
                            title={isClickable ? 'Click to view these results' : undefined}
                          >
                            {msg.content}
                            {isClickable && (
                              <div className="mt-1 flex items-center gap-1 text-xs text-indigo-500">
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                </svg>
                                View results
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}

                  {/* Typing indicator when searching */}
                  {isSearching && (
                    <div className="flex justify-start">
                      <div className="bg-white text-gray-500 px-4 py-2 rounded-2xl rounded-bl-md shadow-sm border border-gray-200">
                        <div className="flex items-center gap-1">
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                        </div>
                      </div>
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </div>

                {/* Input area */}
                <div className="bg-gray-100 px-3 py-2 border-t border-gray-200">
                  <form onSubmit={handleRefinementSubmit} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={refinementInput}
                      onChange={(e) => setRefinementInput(e.target.value)}
                      placeholder="Type a message..."
                      dir="auto"
                      className="flex-1 px-4 py-2 bg-white border border-gray-200 rounded-full
                               text-gray-800 placeholder-gray-400 text-sm outline-none
                               focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/20
                               transition-all duration-200"
                      disabled={isSearching}
                    />
                    <button
                      type="submit"
                      disabled={isSearching || !refinementInput.trim()}
                      className="w-10 h-10 flex items-center justify-center
                               bg-indigo-500 hover:bg-indigo-600
                               disabled:bg-gray-300
                               text-white rounded-full
                               transition-all duration-200 flex-shrink-0"
                    >
                      {isSearching ? (
                        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
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
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                      )}
                    </button>
                  </form>

                  {/* Quick suggestions */}
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {['cheaper options', 'quieter models', 'larger capacity', 'different brands'].map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => setRefinementInput(suggestion)}
                        disabled={isSearching}
                        className="text-xs text-indigo-600 bg-indigo-50 hover:bg-indigo-100
                                 px-2.5 py-1 rounded-full transition-colors disabled:opacity-50
                                 border border-indigo-200"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
