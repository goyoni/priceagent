/**
 * Clean search landing page.
 * Focused, beautiful search experience for finding the best deals.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { trackSearch, trackSellerContact, trackPageView } from '@/lib/analytics';

interface SearchResult {
  seller: string;
  price: number;
  currency: string;
  rating?: number;
  url?: string;
  phone?: string;
  source?: string;
}

interface ProductResult {
  productName: string;
  results: SearchResult[];
}

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<ProductResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searchTime, setSearchTime] = useState<number | null>(null);

  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Track page view
  useEffect(() => {
    trackPageView('/');
  }, []);

  // Poll for trace results
  const pollForResults = async (traceId: string, apiUrl: string): Promise<string> => {
    const maxAttempts = 300; // 5 minutes max
    const pollInterval = 1000; // 1 second

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const response = await fetch(`${apiUrl}/traces/${traceId}`);
        if (!response.ok) {
          // Trace might not exist yet, keep polling
          if (response.status === 404 && attempt < 10) {
            await new Promise(resolve => setTimeout(resolve, pollInterval));
            continue;
          }
          throw new Error('Failed to fetch results');
        }

        const trace = await response.json();

        // Update status message based on current activity
        if (trace.spans && trace.spans.length > 0) {
          const runningSpan = trace.spans.find((s: { status: string }) => s.status === 'running');
          if (runningSpan) {
            setStatusMessage(runningSpan.name || 'Processing...');
          } else {
            setStatusMessage(`Processing... (${trace.spans.length} steps completed)`);
          }
        }

        if (trace.status === 'completed') {
          return trace.final_output || '';
        }

        if (trace.status === 'error') {
          throw new Error(trace.error || 'Search failed');
        }

        // Wait before next poll
        await new Promise(resolve => setTimeout(resolve, pollInterval));
      } catch (err) {
        // Network error - retry a few times
        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, pollInterval));
          continue;
        }
        throw err;
      }
    }

    throw new Error('Search timed out. Check the dashboard for results.');
  };

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isSearching) return;

    setIsSearching(true);
    setError(null);
    setResults([]);
    setStatusMessage('Starting search...');
    const startTime = Date.now();

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';

      // Start the search
      const response = await fetch(`${apiUrl}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent: 'research',
          query: query,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to start search. Please try again.');
      }

      const { trace_id } = await response.json();

      // Poll for results
      const resultText = await pollForResults(trace_id, apiUrl);
      const duration = Date.now() - startTime;
      setSearchTime(duration);
      setStatusMessage(null);

      // Parse results from agent output
      const parsed = parseSearchResults(resultText);
      setResults(parsed);

      // Track search
      trackSearch(
        query,
        parsed.reduce((sum, p) => sum + p.results.length, 0),
        duration
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setStatusMessage(null);
    } finally {
      setIsSearching(false);
    }
  }, [query, isSearching]);

  const handleContact = (seller: string, phone: string) => {
    trackSellerContact(seller, 'whatsapp', query);
    const cleanPhone = phone.replace(/[^0-9+]/g, '');
    const message = encodeURIComponent(`Hi, I'm interested in ${query}. What's your best price?`);
    window.open(`https://wa.me/${cleanPhone}?text=${message}`, '_blank');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Hero Section */}
      <div className={`transition-all duration-500 ${results.length > 0 ? 'pt-8' : 'pt-32'}`}>
        <div className="max-w-4xl mx-auto px-4">
          {/* Logo/Brand */}
          <div className={`text-center mb-8 transition-all duration-500 ${results.length > 0 ? 'scale-75' : ''}`}>
            <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-teal-400 bg-clip-text text-transparent">
              PriceAgent
            </h1>
            <p className={`text-slate-400 mt-2 transition-opacity duration-300 ${results.length > 0 ? 'opacity-0 h-0' : 'opacity-100'}`}>
              Find the best prices. Contact sellers directly.
            </p>
          </div>

          {/* Search Form */}
          <form onSubmit={handleSearch} className="relative">
            <div className="relative group">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search for products (e.g., Samsung refrigerator RF72DG9620B1)"
                className="w-full px-6 py-4 text-lg bg-slate-800/50 border border-slate-700 rounded-2xl
                         text-white placeholder-slate-500 outline-none
                         focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20
                         transition-all duration-300"
                disabled={isSearching}
              />
              <button
                type="submit"
                disabled={isSearching || !query.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 px-6 py-2
                         bg-gradient-to-r from-cyan-500 to-blue-500
                         hover:from-cyan-400 hover:to-blue-400
                         disabled:from-slate-600 disabled:to-slate-600
                         text-white font-medium rounded-xl
                         transition-all duration-300"
              >
                {isSearching ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Searching...
                  </span>
                ) : (
                  'Search'
                )}
              </button>
            </div>

            {/* Status message during search */}
            {isSearching && statusMessage && (
              <div className="text-center mt-4 text-slate-400 text-sm animate-pulse">
                {statusMessage}
              </div>
            )}
          </form>

          {/* Quick suggestions */}
          {results.length === 0 && !isSearching && (
            <div className="flex flex-wrap justify-center gap-2 mt-6">
              {['Samsung refrigerator', 'LG washing machine', 'Bosch oven', 'Apple iPhone 15'].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => setQuery(suggestion)}
                  className="px-4 py-2 text-sm text-slate-400 bg-slate-800/50 rounded-full
                           hover:bg-slate-700 hover:text-white transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Results Section */}
      {(results.length > 0 || error) && (
        <div className="max-w-4xl mx-auto px-4 py-8">
          {error ? (
            <div className="text-center py-12">
              <div className="text-red-400 text-lg">{error}</div>
              <button
                onClick={() => setError(null)}
                className="mt-4 text-cyan-400 hover:underline"
              >
                Try again
              </button>
            </div>
          ) : (
            <>
              {/* Results header */}
              <div className="flex items-center justify-between mb-6">
                <div className="text-slate-400">
                  Found {results.reduce((sum, p) => sum + p.results.length, 0)} results
                  {searchTime && <span className="text-slate-600"> in {(searchTime / 1000).toFixed(1)}s</span>}
                </div>
                <a
                  href="/dashboard"
                  className="text-sm text-cyan-400 hover:underline"
                >
                  Advanced view →
                </a>
              </div>

              {/* Product sections */}
              {results.map((product, pIdx) => (
                <div key={pIdx} className="mb-8">
                  {results.length > 1 && (
                    <h2 className="text-xl font-semibold text-white mb-4">{product.productName}</h2>
                  )}

                  <div className="space-y-3">
                    {product.results.map((result, rIdx) => (
                      <ResultCard
                        key={rIdx}
                        result={result}
                        rank={rIdx + 1}
                        onContact={() => result.phone && handleContact(result.seller, result.phone)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 py-4 text-center text-sm text-slate-600">
        <a href="/dashboard" className="hover:text-slate-400 transition-colors">
          Dashboard
        </a>
        <span className="mx-2">•</span>
        <span>Powered by AI</span>
      </footer>
    </div>
  );
}

// Result Card Component
function ResultCard({
  result,
  rank,
  onContact,
}: {
  result: SearchResult;
  rank: number;
  onContact: () => void;
}) {
  const formatPrice = (price: number, currency: string) => {
    if (currency === 'ILS') {
      return `₪${price.toLocaleString()}`;
    }
    return `${currency} ${price.toLocaleString()}`;
  };

  return (
    <div className="group bg-slate-800/50 border border-slate-700/50 rounded-xl p-4
                    hover:border-cyan-500/30 hover:bg-slate-800/70 transition-all duration-300">
      <div className="flex items-start justify-between gap-4">
        {/* Left: Seller info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center
                           bg-slate-700 rounded-full text-xs text-slate-400">
              {rank}
            </span>
            <div className="min-w-0">
              <h3 className="font-medium text-white truncate">{result.seller}</h3>
              {result.rating && (
                <div className="flex items-center gap-1 text-sm">
                  <span className="text-amber-400">★</span>
                  <span className="text-slate-400">{result.rating.toFixed(1)}</span>
                </div>
              )}
            </div>
          </div>
          {result.source && (
            <span className="inline-block mt-2 px-2 py-0.5 text-xs text-slate-500 bg-slate-700/50 rounded">
              via {result.source}
            </span>
          )}
        </div>

        {/* Right: Price and actions */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-2xl font-bold text-emerald-400">
              {formatPrice(result.price, result.currency)}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {result.url && (
              <a
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-slate-400 hover:text-white hover:bg-slate-700
                         rounded-lg transition-colors"
                title="View product"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            )}
            {result.phone && (
              <button
                onClick={onContact}
                className="flex items-center gap-2 px-4 py-2
                         bg-emerald-500/20 text-emerald-400
                         hover:bg-emerald-500 hover:text-white
                         rounded-lg transition-all duration-300"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
                </svg>
                Contact
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Parse search results from agent output
function parseSearchResults(text: string): ProductResult[] {
  const results: ProductResult[] = [];

  // Simple parsing - extract numbered results
  const lines = text.split('\n');
  const currentProduct: ProductResult = { productName: 'Search Results', results: [] };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();

    // Match result pattern: "1. Seller Name (Rating: 4.5/5)"
    const resultMatch = line.match(/^(\d+)\.\s+(.+?)(?:\s+\(Rating:\s*([\d.]+)\/5\))?$/);
    if (resultMatch) {
      const seller = resultMatch[2].trim();
      const rating = resultMatch[3] ? parseFloat(resultMatch[3]) : undefined;

      // Look for price, URL, contact in following lines
      let price = 0;
      let currency = 'ILS';
      let url: string | undefined;
      let phone: string | undefined;
      let source: string | undefined;

      // Parse following lines for details
      for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
        const detailLine = lines[j].trim();

        const priceMatch = detailLine.match(/Price:\s*([\d,]+)\s*(\w+)?/);
        if (priceMatch) {
          price = parseInt(priceMatch[1].replace(/,/g, ''));
          currency = priceMatch[2] || 'ILS';
        }

        const urlMatch = detailLine.match(/URL:\s*(https?:\/\/[^\s]+)/);
        if (urlMatch) url = urlMatch[1];

        const contactMatch = detailLine.match(/Contact:\s*(\+?[\d\s-]+)/);
        if (contactMatch) phone = contactMatch[1].replace(/[\s-]/g, '');

        // Check for source in the seller line (e.g., "[zap]")
        const sourceMatch = line.match(/\[([^\]]+)\]/);
        if (sourceMatch) source = sourceMatch[1];
      }

      if (price > 0) {
        currentProduct.results.push({
          seller,
          price,
          currency,
          rating,
          url,
          phone,
          source,
        });
      }
    }

    i++;
  }

  if (currentProduct.results.length > 0) {
    results.push(currentProduct);
  }

  return results;
}
