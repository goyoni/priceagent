/**
 * ProductDiscoveryView component for AI-powered product recommendations.
 * Allows users to describe what they need in natural language.
 */

'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useDiscoveryStore } from '@/stores/useDiscoveryStore';
import { DiscoveryResultsTable } from './DiscoveryResultsTable';
import { CountrySelector } from '@/components/ui/CountrySelector';
import type { DiscoveredProduct, ShoppingListItem } from '@/lib/types';

interface ProductDiscoveryViewProps {
  onAddToShoppingList: (item: Omit<ShoppingListItem, 'id' | 'added_at'>) => void;
  country: string;
  onCountryChange?: (country: string) => void;
}

/**
 * Parse discovery products from agent output.
 */
function parseDiscoveryProducts(output: string): DiscoveredProduct[] {
  try {
    // Try to parse as JSON directly
    const parsed = JSON.parse(output);

    if (parsed.products && Array.isArray(parsed.products)) {
      return parsed.products.map((p: Record<string, unknown>, index: number): DiscoveredProduct => ({
        id: String(p.id || `prod_${Date.now()}_${index}`),
        name: String(p.name || 'Unknown Product'),
        brand: p.brand ? String(p.brand) : undefined,
        model_number: p.model_number ? String(p.model_number) : undefined,
        category: String(p.category || 'product'),
        key_specs: Array.isArray(p.key_specs) ? p.key_specs.map(String) : [],
        price_range: p.price_range ? String(p.price_range) : undefined,
        why_recommended: String(p.why_recommended || ''),
        price: typeof p.price === 'number' ? p.price : undefined,
        currency: p.currency ? String(p.currency) : undefined,
        url: p.url ? String(p.url) : undefined,
        rating: typeof p.rating === 'number' ? p.rating : undefined,
      }));
    }

    if (Array.isArray(parsed)) {
      return parsed.map((p: Record<string, unknown>, index: number): DiscoveredProduct => ({
        id: String(p.id || `prod_${Date.now()}_${index}`),
        name: String(p.name || 'Unknown Product'),
        brand: p.brand ? String(p.brand) : undefined,
        model_number: p.model_number ? String(p.model_number) : undefined,
        category: String(p.category || 'product'),
        key_specs: Array.isArray(p.key_specs) ? p.key_specs.map(String) : [],
        price_range: p.price_range ? String(p.price_range) : undefined,
        why_recommended: String(p.why_recommended || ''),
        price: typeof p.price === 'number' ? p.price : undefined,
        currency: p.currency ? String(p.currency) : undefined,
        url: p.url ? String(p.url) : undefined,
        rating: typeof p.rating === 'number' ? p.rating : undefined,
      }));
    }

    console.log('[Discovery] Output is not a products array:', parsed);
    return [];
  } catch (e) {
    // Try to extract JSON from markdown or mixed content
    const jsonMatch = output.match(/\{[\s\S]*"products"[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        if (parsed.products && Array.isArray(parsed.products)) {
          return parseDiscoveryProducts(JSON.stringify(parsed));
        }
      } catch {
        console.log('[Discovery] Failed to extract JSON from output');
      }
    }

    console.log('[Discovery] Failed to parse output as JSON:', e);
    return [];
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
    isSearching,
    currentTraceId,
    products,
    error,
    statusMessage,
    setStatusMessage,
    setError,
    runDiscovery,
    setSearchComplete,
    clearResults,
  } = useDiscoveryStore();

  const [addingProductId, setAddingProductId] = useState<string | undefined>();
  const [localQuery, setLocalQuery] = useState(query);
  const wsRef = useRef<WebSocket | null>(null);

  // Example queries for suggestions
  const exampleQueries = [
    'Silent refrigerator for family of 4',
    'Energy efficient washing machine for small apartment',
    'Quiet dishwasher with good drying',
    'Large capacity oven for baking',
  ];

  // WebSocket listener for trace completion
  useEffect(() => {
    if (!currentTraceId || !isSearching) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    const wsUrl = apiUrl.replace('http', 'ws') || 'ws://localhost:8000';

    console.log('[Discovery] Connecting WebSocket for trace:', currentTraceId);

    const ws = new WebSocket(`${wsUrl}/traces/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Discovery] WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Only process events for our trace
        if (data.trace_id !== currentTraceId) return;

        // Update status message from span events
        if (data.event_type === 'span_started' && data.data?.name) {
          setStatusMessage(data.data.name);
        }

        // Handle trace completion
        if (data.event_type === 'trace_ended') {
          console.log('[Discovery] Trace completed:', currentTraceId);

          if (data.data?.error) {
            console.error('[Discovery] Trace error:', data.data.error);
            setError(data.data.error);
            setSearchComplete([]);
          } else {
            const finalOutput = data.data?.final_output || '';
            console.log('[Discovery] Final output length:', finalOutput.length);
            console.log('[Discovery] Final output preview:', finalOutput.substring(0, 500));

            const products = parseDiscoveryProducts(finalOutput);
            console.log('[Discovery] Parsed products:', products.length);

            if (products.length === 0 && finalOutput.length > 0) {
              console.log('[Discovery] No products parsed, full output:', finalOutput);
            }

            setSearchComplete(products);
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
      console.log('[Discovery] WebSocket closed');

      // If still searching when WebSocket closes, try to fetch trace directly
      if (isSearching && currentTraceId) {
        console.log('[Discovery] Fetching trace directly as fallback');
        fetch(`${apiUrl}/traces/${currentTraceId}`)
          .then((res) => res.json())
          .then((trace) => {
            if (trace.status === 'completed' && trace.final_output) {
              const products = parseDiscoveryProducts(trace.final_output);
              setSearchComplete(products);
            } else if (trace.status === 'error') {
              setError(trace.error || 'Discovery failed');
              setSearchComplete([]);
            }
          })
          .catch((err) => {
            console.error('[Discovery] Fallback fetch failed:', err);
          });
      }
    };

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [currentTraceId, isSearching, setStatusMessage, setError, setSearchComplete]);

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!localQuery.trim() || isSearching) return;

    try {
      await runDiscovery(localQuery);
    } catch (err) {
      console.error('[Discovery] Search failed:', err);
    }
  }, [localQuery, isSearching, runDiscovery]);

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

  return (
    <div className="space-y-6">
      {/* Discovery Form */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h2 className="text-xl font-semibold text-white mb-2">
          What are you looking for?
        </h2>
        <p className="text-slate-400 text-sm mb-4">
          Describe your needs in natural language - our AI will find the best products for you.
        </p>

        <form onSubmit={handleSearch} className="space-y-4">
          <textarea
            value={localQuery}
            onChange={(e) => setLocalQuery(e.target.value)}
            placeholder="Example: I need a silent refrigerator for a family of 4 with an open kitchen layout"
            className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600 rounded-xl
                     text-white placeholder-slate-500 outline-none resize-none
                     focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20
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
              <div className="text-xs text-slate-500">
                Country: {country}
              </div>
            )}
            <button
              type="submit"
              disabled={isSearching || !localQuery.trim()}
              className="px-6 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-500
                       hover:from-cyan-400 hover:to-blue-400
                       disabled:from-slate-600 disabled:to-slate-600
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
          <div className="mt-4 text-center text-slate-400 text-sm animate-pulse">
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

      {/* Suggestions (when no results) */}
      {!isSearching && products.length === 0 && !error && (
        <div className="text-center">
          <p className="text-slate-500 text-sm mb-3">Or try one of these examples:</p>
          <div className="flex flex-wrap justify-center gap-2">
            {exampleQueries.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => handleSuggestionClick(suggestion)}
                className="px-3 py-1.5 text-sm text-slate-400 bg-slate-800/50 rounded-lg
                         hover:bg-slate-700 hover:text-white transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {products.length > 0 && (
        <div className="bg-slate-800/30 border border-slate-700 rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="text-slate-400 text-sm">
              Found {products.length} recommended products
            </span>
            <button
              onClick={clearResults}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear results
            </button>
          </div>

          <DiscoveryResultsTable
            products={products}
            onAddToList={handleAddToList}
            isAddingId={addingProductId}
          />
        </div>
      )}
    </div>
  );
}
