/**
 * Clean search landing page.
 * Focused, beautiful search experience for finding the best deals.
 * Search history stored in browser localStorage.
 * URL params preserve search state for sharing/refresh.
 */

'use client';

import { useState, useEffect, useCallback, Suspense, useMemo } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { trackSearch, trackSellerContact, trackPageView } from '@/lib/analytics';
import {
  SearchHistoryItem,
  getSearchHistory,
  addToSearchHistory,
  deleteFromHistory,
  clearSearchHistory,
  formatRelativeTime,
} from '@/lib/searchHistory';
import type { DiscoveryHistoryItem } from '@/lib/discoveryHistory';
import { api } from '@/lib/api';
import { useDraftStore } from '@/stores/useDraftStore';
import { DraftModal } from '@/components/drafts/DraftModal';
import { ProductDiscoveryView } from '@/components/discovery/ProductDiscoveryView';
import { ShoppingListView } from '@/components/shopping-list/ShoppingListView';
import { PriceSearchNotification } from '@/components/shopping-list/PriceSearchNotification';
import { useCountry } from '@/hooks/useCountry';
import { useShoppingListStore } from '@/stores/useShoppingListStore';
import { useDiscoveryStore } from '@/stores/useDiscoveryStore';
import type { ShoppingListItem } from '@/lib/types';

// Tab types for the landing page
type PageTab = 'search' | 'discover' | 'shopping-list';

// Format time ago from ISO date string
function formatTimeAgo(isoDate: string): string {
  const timestamp = new Date(isoDate).getTime();
  return formatRelativeTime(timestamp);
}

// Extract domain from URL for seller lookup
function extractDomain(url: string): string | null {
  try {
    const parsed = new URL(url);
    let domain = parsed.hostname.toLowerCase();
    if (domain.startsWith('www.')) {
      domain = domain.slice(4);
    }
    if (domain.includes('google.com')) {
      return null;
    }
    return domain;
  } catch {
    return null;
  }
}

// Normalize store name for matching
function normalizeStoreName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[|]/g, ' ')
    .replace(/[^\w\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

// Normalize without spaces for looser matching
function normalizeNoSpaces(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^\w]/g, '');
}

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

// Bundle opportunity from multi-product search
interface BundleResult {
  storeName: string;
  rating?: number;
  productCount: number;
  totalProducts: number;
  products: Array<{
    name: string;
    price: number;
    currency: string;
    url?: string;
  }>;
  totalPrice: number;
  contact?: string;
}

// Selected seller for bulk messaging
interface SelectedSeller {
  id: string;
  name: string;
  phone: string;
  price?: number;
  productName?: string;
}

// Wrapper component with Suspense for useSearchParams
export default function SearchPage() {
  return (
    <Suspense fallback={<SearchPageLoading />}>
      <SearchPageContent />
    </Suspense>
  );
}

// Loading fallback
function SearchPageLoading() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-teal-400 bg-clip-text text-transparent">
          Shopping Agent
        </h1>
        <p className="text-slate-400 mt-4 animate-pulse">Loading...</p>
      </div>
    </div>
  );
}

// Server trace item from API
interface ServerTrace {
  id: string;
  input_prompt: string;
  status: string;
  started_at: string;
  total_duration_ms: number | null;
}

// Main content component
function SearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Tab state - default to 'discover' (Find Products)
  const [activeTab, setActiveTab] = useState<PageTab>('discover');

  // Country detection
  const { country, setCountry } = useCountry('IL');

  // Shopping list from store
  const {
    items: shoppingList,
    addItem: addToShoppingList,
    activeSearchSession,
    markSearchComplete,
  } = useShoppingListStore();

  // Discovery history from store
  const {
    history: discoveryHistory,
    loadHistory: loadDiscoveryHistory,
    loadFromTrace: loadDiscoveryFromTrace,
  } = useDiscoveryStore();

  const [query, setQuery] = useState('');
  const [currentTraceId, setCurrentTraceId] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingTrace, setIsLoadingTrace] = useState(false);
  const [results, setResults] = useState<ProductResult[]>([]);
  const [bundles, setBundles] = useState<BundleResult[]>([]);
  const [selectedSellers, setSelectedSellers] = useState<SelectedSeller[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searchTime, setSearchTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [rawResultText, setRawResultText] = useState<string | null>(null);

  // History state
  const [recentTraces, setRecentTraces] = useState<ServerTrace[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>([]);

  // Seller lookup state for enriching results with phone numbers
  const [sellersByDomain, setSellersByDomain] = useState<Record<string, string>>({});
  const [sellersByName, setSellersByName] = useState<Record<string, string>>({});
  const [sellersByNameNoSpaces, setSellersByNameNoSpaces] = useState<Record<string, string>>({});

  // Draft store for bulk messaging modal
  const { generateDrafts, isGenerating: isGeneratingDrafts } = useDraftStore();

  // Load localStorage history on mount
  useEffect(() => {
    setSearchHistory(getSearchHistory());
    loadDiscoveryHistory();
  }, [loadDiscoveryHistory]);

  // Listen for price search trace completion via WebSocket
  useEffect(() => {
    if (!activeSearchSession?.trace_id || activeSearchSession.status !== 'running') {
      return;
    }

    const traceId = activeSearchSession.trace_id;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const wsUrl = apiUrl.replace('http://', 'ws://').replace('https://', 'wss://');

    let ws: WebSocket | null = null;
    let cleanup = () => {
      if (ws) {
        ws.close();
        ws = null;
      }
    };

    try {
      ws = new WebSocket(`${wsUrl}/traces/ws`);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.trace_id !== traceId) return;

          if (data.event_type === 'trace_ended') {
            console.log('[PriceSearch] Trace completed:', traceId);
            if (data.data?.error) {
              markSearchComplete('failed', data.data.error);
            } else {
              markSearchComplete('completed');
            }
            cleanup();
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onerror = () => {
        console.error('[PriceSearch] WebSocket error');
        markSearchComplete('failed', 'Connection error');
        cleanup();
      };

    } catch (err) {
      console.error('[PriceSearch] Failed to connect WebSocket:', err);
    }

    return cleanup;
  }, [activeSearchSession?.trace_id, activeSearchSession?.status, markSearchComplete]);

  // Load sellers for phone enrichment on mount
  useEffect(() => {
    api.getSellers()
      .then((sellers) => {
        const byDomain: Record<string, string> = {};
        const byName: Record<string, string> = {};
        const byNameNoSpaces: Record<string, string> = {};

        sellers.forEach((s) => {
          const phone = s.whatsapp_number || s.phone_number;
          if (phone) {
            // Add by domain
            if (s.domain) {
              byDomain[s.domain] = phone;
            }
            // Add by normalized name
            const normalizedName = normalizeStoreName(s.seller_name);
            byName[normalizedName] = phone;
            // Add by no-spaces name
            const noSpacesName = normalizeNoSpaces(s.seller_name);
            byNameNoSpaces[noSpacesName] = phone;
          }
        });

        setSellersByDomain(byDomain);
        setSellersByName(byName);
        setSellersByNameNoSpaces(byNameNoSpaces);
        console.log('[Sellers] Loaded', sellers.length, 'sellers for enrichment');
      })
      .catch((err) => {
        console.error('[Sellers] Failed to load sellers:', err);
      });
  }, []);

  // Track page view
  useEffect(() => {
    trackPageView('/');
  }, []);

  // Helper to find contact for a seller by domain or name
  const findContact = useCallback((storeName: string, url?: string): string | undefined => {
    // First try by domain
    if (url) {
      const domain = extractDomain(url);
      if (domain && sellersByDomain[domain]) {
        return sellersByDomain[domain];
      }
    }

    // Then try by name (with spaces)
    const normalizedName = normalizeStoreName(storeName);
    if (sellersByName[normalizedName]) {
      return sellersByName[normalizedName];
    }

    // Check for partial matches
    for (const [name, phone] of Object.entries(sellersByName)) {
      if (normalizedName.includes(name) || name.includes(normalizedName)) {
        return phone;
      }
    }

    // Try no-spaces matching
    const noSpacesName = normalizeNoSpaces(storeName);
    if (sellersByNameNoSpaces[noSpacesName]) {
      return sellersByNameNoSpaces[noSpacesName];
    }

    // Check for partial no-spaces matches
    for (const [name, phone] of Object.entries(sellersByNameNoSpaces)) {
      if (noSpacesName.includes(name) || name.includes(noSpacesName)) {
        return phone;
      }
    }

    return undefined;
  }, [sellersByDomain, sellersByName, sellersByNameNoSpaces]);

  // Enrich results with phone numbers from sellers database
  const enrichResults = useCallback((productResults: ProductResult[]): ProductResult[] => {
    return productResults.map(section => ({
      ...section,
      results: section.results.map(r => {
        if (r.phone) return r;
        const phone = findContact(r.seller, r.url);
        return phone ? { ...r, phone } : r;
      }),
    }));
  }, [findContact]);

  // Enrich bundles with phone numbers from sellers database
  const enrichBundles = useCallback((bundleResults: BundleResult[]): BundleResult[] => {
    return bundleResults.map(bundle => {
      if (bundle.contact) return bundle;
      const contact = findContact(bundle.storeName, bundle.products?.[0]?.url);
      return contact ? { ...bundle, contact } : bundle;
    });
  }, [findContact]);

  // Re-enrich results when sellers become available (handles race condition on page load)
  const sellersLoaded = Object.keys(sellersByDomain).length > 0 || Object.keys(sellersByName).length > 0;
  useEffect(() => {
    if (sellersLoaded && results.length > 0) {
      // Check if any results are missing phone numbers that could be enriched
      const needsEnrichment = results.some(section =>
        section.results.some(r => !r.phone && (r.url || r.seller))
      );
      if (needsEnrichment) {
        console.log('[Enrichment] Re-enriching results with seller data');
        setResults(prev => enrichResults(prev));
      }
    }
    if (sellersLoaded && bundles.length > 0) {
      const needsEnrichment = bundles.some(b => !b.contact && (b.storeName || b.products?.[0]?.url));
      if (needsEnrichment) {
        console.log('[Enrichment] Re-enriching bundles with seller data');
        setBundles(prev => enrichBundles(prev));
      }
    }
  }, [sellersLoaded]); // Only run when sellers load status changes

  // Fetch recent traces from server
  const fetchRecentTraces = async () => {
    setIsLoadingHistory(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const response = await fetch(`${apiUrl}/traces/?limit=20`);
      if (response.ok) {
        const data = await response.json();
        // Filter to only completed traces, excluding test traces
        const completed = (data.traces || []).filter(
          (t: ServerTrace) =>
            t.status === 'completed' &&
            !t.input_prompt.toLowerCase().includes('test')
        );
        setRecentTraces(completed);
      }
    } catch (err) {
      console.error('[History] Failed to fetch traces:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // Fetch recent traces on mount
  useEffect(() => {
    fetchRecentTraces();
  }, []);

  // Load trace from URL parameter on mount
  useEffect(() => {
    const traceId = searchParams.get('trace');
    if (traceId && traceId !== currentTraceId) {
      loadTraceResults(traceId);
    }
  }, [searchParams]);

  // Function to load results from an existing trace
  const loadTraceResults = async (traceId: string) => {
    console.log('[LoadTrace] Starting load for trace:', traceId);
    setIsLoadingTrace(true);
    setError(null);
    setResults([]);
    setBundles([]);
    setSelectedSellers([]);
    setRawResultText(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      console.log('[LoadTrace] Fetching from:', `${apiUrl}/traces/${traceId}`);
      const response = await fetch(`${apiUrl}/traces/${traceId}`);

      if (!response.ok) {
        console.error('[LoadTrace] Response not ok:', response.status);
        throw new Error('Trace not found');
      }

      const trace = await response.json();
      console.log('[LoadTrace] Got trace:', trace.status, 'has final_output:', !!trace.final_output, 'spans:', trace.spans?.length);

      if (trace.status === 'completed') {
        setQuery(trace.input_prompt.replace('Search for: ', ''));
        setCurrentTraceId(traceId);
        setSearchTime(trace.total_duration_ms);

        // Look for search tool output in spans (like dashboard does)
        const searchSpans = (trace.spans || []).filter(
          (s: { span_type: string; tool_name?: string; tool_output?: string }) =>
            s.span_type === 'tool_call' &&
            (s.tool_name === 'search_products' || s.tool_name === 'search_multiple_products' || s.tool_name === 'search_aggregators') &&
            s.tool_output
        );

        console.log('[LoadTrace] Found search spans:', searchSpans.length);

        if (searchSpans.length > 0) {
          // Parse from search tool output (structured format)
          const allResults: ProductResult[] = [];

          for (const span of searchSpans) {
            const toolOutput = span.tool_output as string;
            setRawResultText(toolOutput);

            // Check if multi-product with sections
            const sectionPattern = /\n=== ([^=\n]+) ===\n/g;
            const sections: Array<{ name: string; startIndex: number }> = [];
            let match;

            while ((match = sectionPattern.exec(toolOutput)) !== null) {
              if (!match[1].includes('BUNDLE')) {
                sections.push({ name: match[1].trim(), startIndex: match.index + match[0].length });
              }
            }

            if (sections.length > 0) {
              // Multi-product format
              for (let i = 0; i < sections.length; i++) {
                const startIdx = sections[i].startIndex;
                const endIdx = i + 1 < sections.length
                  ? toolOutput.indexOf('\n===', startIdx)
                  : toolOutput.length;

                const sectionText = toolOutput.slice(startIdx, endIdx > 0 ? endIdx : undefined);
                const results = parseToolOutput(sectionText);

                if (results.length > 0) {
                  allResults.push({
                    productName: sections[i].name,
                    results,
                  });
                }
              }
            } else {
              // Single product - get query from tool_input
              let productQuery = 'Search Results';
              if (span.tool_input) {
                try {
                  const input = typeof span.tool_input === 'string'
                    ? JSON.parse(span.tool_input)
                    : span.tool_input;
                  if (input.query) productQuery = input.query;
                } catch { /* ignore parse error */ }
              }

              const results = parseToolOutput(toolOutput);
              if (results.length > 0) {
                allResults.push({
                  productName: productQuery,
                  results,
                });
              }
            }

            // Parse bundle opportunities from multi-product search
            const parsedBundles = parseBundleSection(toolOutput);
            if (parsedBundles.length > 0) {
              setBundles(enrichBundles(parsedBundles));
              console.log('[LoadTrace] Found bundles:', parsedBundles.length);
            }
          }

          setResults(enrichResults(allResults));
          console.log('[LoadTrace] Parsed results:', allResults.length, 'products');
        } else if (trace.final_output) {
          // Fallback to final_output
          setRawResultText(trace.final_output);
          const parsed = parseSearchResults(trace.final_output);
          setResults(enrichResults(parsed));
          console.log('[LoadTrace] Parsed from final_output:', parsed.length);
        } else {
          setError('Search completed but no results found');
        }
      } else if (trace.status === 'error') {
        setError(trace.error || 'Search failed');
      } else if (trace.status === 'running') {
        setError('This search is still running. Please wait...');
      } else {
        console.log('[LoadTrace] Unknown status:', trace.status);
        setError('Could not load results');
      }
    } catch (err) {
      console.error('[LoadTrace] Error:', err);
      setError('Could not load search results');
      // Clear the invalid trace param from URL
      router.replace('/', { scroll: false });
    } finally {
      setIsLoadingTrace(false);
    }
  };

  // Update URL with trace ID
  const updateUrlWithTrace = (traceId: string) => {
    const newUrl = `/?trace=${traceId}`;
    router.replace(newUrl, { scroll: false });
    setCurrentTraceId(traceId);
  };

  // Elapsed time counter during search
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (isSearching) {
      setElapsedTime(0);
      interval = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isSearching]);

  // Wait for trace completion via WebSocket
  const waitForResults = (traceId: string, apiUrl: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      const wsUrl = apiUrl.replace('http://', 'ws://').replace('https://', 'wss://') ||
                    `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

      const ws = new WebSocket(`${wsUrl}/traces/ws`);
      let resolved = false;

      const cleanup = () => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };

      ws.onopen = () => {
        setStatusMessage('Connected, waiting for results...');
      };

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);

          // Only care about events for our trace
          if (data.trace_id !== traceId) return;

          if (data.event_type === 'span_started' || data.event_type === 'span_ended') {
            // Update status with current activity - make it user-friendly
            const spanName = data.data?.name || '';
            const spanType = data.data?.type || data.data?.span_type || '';

            let friendlyStatus = spanName;

            // Make status messages more user-friendly
            if (spanName.includes('search_products') || spanName.includes('search_aggregators')) {
              friendlyStatus = '🔍 Searching price comparison sites...';
            } else if (spanName.includes('google_shopping') || spanName.includes('GoogleShopping')) {
              friendlyStatus = '🛒 Searching Google Shopping...';
            } else if (spanName.includes('google_search') || spanName.includes('GoogleSearch')) {
              friendlyStatus = '🔎 Searching Google...';
            } else if (spanName.includes('zap') || spanName.includes('Zap')) {
              friendlyStatus = '🏪 Searching Zap.co.il...';
            } else if (spanName.includes('wisebuy') || spanName.includes('WiseBuy')) {
              friendlyStatus = '💡 Searching WiseBuy...';
            } else if (spanName.includes('extract') || spanName.includes('scrape')) {
              friendlyStatus = '📄 Extracting product details...';
            } else if (spanType === 'llm_call') {
              friendlyStatus = '🤖 AI is analyzing results...';
            } else if (spanType === 'agent' || spanType === 'agent_run') {
              friendlyStatus = '🔄 Processing...';
            } else if (spanName) {
              // Show span name but clean it up
              friendlyStatus = spanName.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase());
            }

            setStatusMessage(friendlyStatus);
          }

          if (data.event_type === 'trace_ended') {
            resolved = true;
            cleanup();

            console.log('[WebSocket] trace_ended received:', data);
            console.log('[WebSocket] final_output:', data.data?.final_output);

            if (data.data?.error) {
              reject(new Error(data.data.error));
            } else {
              resolve(data.data?.final_output || '');
            }
          }
        } catch (err) {
          console.error('WebSocket message parse error:', err);
        }
      };

      ws.onerror = () => {
        if (!resolved) {
          cleanup();
          reject(new Error('WebSocket connection failed'));
        }
      };

      ws.onclose = () => {
        if (!resolved) {
          // Fallback: fetch the trace directly
          fetch(`${apiUrl}/traces/${traceId}`)
            .then((res: Response) => res.json())
            .then((trace: { status: string; final_output?: string; error?: string }) => {
              if (trace.status === 'completed') {
                resolve(trace.final_output || '');
              } else if (trace.status === 'error') {
                reject(new Error(trace.error || 'Search failed'));
              } else {
                reject(new Error('Connection lost. Check the dashboard for results.'));
              }
            })
            .catch(() => reject(new Error('Connection lost. Check the dashboard for results.')));
        }
      };
    });
  };

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isSearching) return;

    setIsSearching(true);
    setError(null);
    setResults([]);
    setBundles([]);
    setSelectedSellers([]);
    setRawResultText(null);
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

      // Wait for completion via WebSocket (just to know when it's done)
      await waitForResults(trace_id, apiUrl);
      const duration = Date.now() - startTime;
      setSearchTime(duration);
      setStatusMessage(null);

      // Update URL first
      updateUrlWithTrace(trace_id);

      // Load full trace with spans to get structured data
      // (This is the same logic as clicking history - parse from tool output)
      const traceResponse = await fetch(`${apiUrl}/traces/${trace_id}`);
      if (traceResponse.ok) {
        const trace = await traceResponse.json();

        // Find search tool spans
        const searchSpans = (trace.spans || []).filter(
          (s: { span_type: string; tool_name?: string; tool_output?: string }) =>
            s.span_type === 'tool_call' &&
            (s.tool_name === 'search_products' || s.tool_name === 'search_multiple_products') &&
            s.tool_output
        );

        if (searchSpans.length > 0) {
          const allResults: ProductResult[] = [];

          for (const span of searchSpans) {
            const toolOutput = span.tool_output as string;
            setRawResultText(toolOutput);

            // Check if multi-product with sections
            const sectionPattern = /\n=== ([^=\n]+) ===\n/g;
            const sections: Array<{ name: string; startIndex: number }> = [];
            let match;

            while ((match = sectionPattern.exec(toolOutput)) !== null) {
              if (!match[1].includes('BUNDLE')) {
                sections.push({ name: match[1].trim(), startIndex: match.index + match[0].length });
              }
            }

            if (sections.length > 0) {
              for (let i = 0; i < sections.length; i++) {
                const startIdx = sections[i].startIndex;
                const endIdx = i + 1 < sections.length
                  ? toolOutput.indexOf('\n===', startIdx)
                  : toolOutput.length;
                const sectionText = toolOutput.slice(startIdx, endIdx > 0 ? endIdx : undefined);
                const results = parseToolOutput(sectionText);
                if (results.length > 0) {
                  allResults.push({ productName: sections[i].name, results });
                }
              }
            } else {
              let productQuery = query;
              if (span.tool_input) {
                try {
                  const input = typeof span.tool_input === 'string'
                    ? JSON.parse(span.tool_input)
                    : span.tool_input;
                  if (input.query) productQuery = input.query;
                } catch { /* ignore */ }
              }
              const results = parseToolOutput(toolOutput);
              if (results.length > 0) {
                allResults.push({ productName: productQuery, results });
              }
            }

            // Parse bundle opportunities from multi-product search
            const parsedBundles = parseBundleSection(toolOutput);
            if (parsedBundles.length > 0) {
              setBundles(enrichBundles(parsedBundles));
              console.log('[Search] Found bundles:', parsedBundles.length);
            }
          }

          setResults(enrichResults(allResults));
          console.log('[Search] Parsed from tool output:', allResults.length, 'products');

          // Track and save
          const totalResults = allResults.reduce((sum, p) => sum + p.results.length, 0);
          trackSearch(query, totalResults, duration);

          const historyItem = addToSearchHistory({
            query,
            timestamp: Date.now(),
            resultCount: totalResults,
            searchTimeMs: duration,
            traceId: trace_id,
            topResults: allResults[0]?.results.slice(0, 3).map(r => ({
              seller: r.seller,
              price: r.price,
              currency: r.currency,
            })),
          });
          setSearchHistory(prev => [historyItem, ...prev.slice(0, 49)]);
        } else if (trace.final_output) {
          // Fallback to final_output
          setRawResultText(trace.final_output);
          const parsed = parseSearchResults(trace.final_output);
          setResults(enrichResults(parsed));

          const totalResults = parsed.reduce((sum, p) => sum + p.results.length, 0);
          trackSearch(query, totalResults, duration);

          const historyItem = addToSearchHistory({
            query,
            timestamp: Date.now(),
            resultCount: totalResults,
            searchTimeMs: duration,
            traceId: trace_id,
            topResults: parsed[0]?.results.slice(0, 3).map(r => ({
              seller: r.seller,
              price: r.price,
              currency: r.currency,
            })),
          });
          setSearchHistory(prev => [historyItem, ...prev.slice(0, 49)]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setStatusMessage(null);
    } finally {
      setIsSearching(false);
    }
  }, [query, isSearching]);

  const handleHistoryClick = (trace: ServerTrace) => {
    console.log('[History] Clicked trace:', trace.id, trace.input_prompt);
    updateUrlWithTrace(trace.id);
    loadTraceResults(trace.id);
  };

  // Handle click on localStorage history item
  const handleLocalHistoryClick = (item: SearchHistoryItem) => {
    console.log('[LocalHistory] Clicked item:', item.id, item.query, 'traceId:', item.traceId);
    // Switch to search tab to show results
    setActiveTab('search');
    if (item.traceId) {
      updateUrlWithTrace(item.traceId);
      loadTraceResults(item.traceId);
    } else {
      // No trace ID - just set the query for a new search
      setQuery(item.query);
    }
  };

  const handleDeleteHistory = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    // Delete trace from server
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    fetch(`${apiUrl}/traces/${id}`, { method: 'DELETE' })
      .then(() => {
        setRecentTraces(prev => prev.filter(t => t.id !== id));
      })
      .catch(err => console.error('[History] Delete failed:', err));
  };

  // Handle click on discovery history item
  const handleDiscoveryHistoryClick = (item: DiscoveryHistoryItem) => {
    console.log('[DiscoveryHistory] Clicked item:', item.id, item.query, 'traceId:', item.traceId);
    // Switch to discover tab to show results
    setActiveTab('discover');
    if (item.traceId) {
      loadDiscoveryFromTrace(item.traceId, item.query);
    }
  };

  // Selection handlers for bulk messaging
  const toggleSellerSelection = (seller: SelectedSeller) => {
    setSelectedSellers(prev => {
      const exists = prev.find(s => s.id === seller.id);
      if (exists) {
        return prev.filter(s => s.id !== seller.id);
      }
      return [...prev, seller];
    });
  };

  const isSellerSelected = (id: string) => {
    return selectedSellers.some(s => s.id === id);
  };

  const clearSelection = () => {
    setSelectedSellers([]);
  };

  const sendBulkWhatsApp = () => {
    if (selectedSellers.length === 0) return;

    // Convert selected sellers to the format expected by generateDrafts
    const sellersForDrafts = selectedSellers.map(seller => ({
      seller_name: seller.name,
      phone_number: seller.phone,
      product_name: seller.productName || query,
      listed_price: seller.price || 0,
    }));

    // Generate drafts and open modal for editing before sending
    generateDrafts(sellersForDrafts);
  };

  const handleContact = (seller: string, phone: string) => {
    trackSellerContact(seller, 'whatsapp', query);
    const cleanPhone = phone.replace(/[^0-9+]/g, '');
    const message = encodeURIComponent(`Hi, I'm interested in ${query}. What's your best price?`);
    window.open(`https://wa.me/${cleanPhone}?text=${message}`, '_blank');
  };

  // Handler for adding items to shopping list from discovery
  const handleAddToShoppingList = useCallback((item: Omit<ShoppingListItem, 'id' | 'added_at'>) => {
    const newItem = addToShoppingList(item);
    console.log('[ShoppingList] Added item:', newItem.product_name);
  }, [addToShoppingList]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex">
      {/* Fixed Left Sidebar */}
      <aside className="fixed top-0 left-0 h-full w-64 bg-slate-900 border-r border-slate-700 flex flex-col z-40">
        {/* Sidebar Header - Logo and Brand */}
        <div className="p-4 border-b border-slate-700">
          {/* App Logo - matches favicon design */}
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 flex items-center justify-center">
              <svg className="w-10 h-10" viewBox="0 0 64 64" fill="none">
                {/* Shopping bag body */}
                <path d="M12 20 L8 58 C8 60 10 62 12 62 L52 62 C54 62 56 60 56 58 L52 20 Z"
                      fill="#6366f1" stroke="#4f46e5" strokeWidth="2"/>
                {/* Bag handles */}
                <path d="M22 20 C22 12 26 6 32 6 C38 6 42 12 42 20"
                      fill="none" stroke="#4f46e5" strokeWidth="3" strokeLinecap="round"/>
                {/* Left eye */}
                <circle cx="24" cy="36" r="5" fill="#22d3ee"/>
                <circle cx="24" cy="36" r="2" fill="#0e7490"/>
                {/* Right eye */}
                <circle cx="40" cy="36" r="5" fill="#22d3ee"/>
                <circle cx="40" cy="36" r="2" fill="#0e7490"/>
                {/* Smiling mouth */}
                <path d="M24 46 Q32 54 40 46"
                      fill="none" stroke="#22d3ee" strokeWidth="2.5" strokeLinecap="round"/>
                {/* Antenna */}
                <circle cx="32" cy="4" r="3" fill="#22d3ee"/>
                <line x1="32" y1="6" x2="32" y2="12" stroke="#22d3ee" strokeWidth="2"/>
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-teal-400 bg-clip-text text-transparent">
                Shopping Agent
              </h1>
            </div>
          </div>
          {/* Claude Badge */}
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
            </svg>
            <span>Built with Claude</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <nav className="p-3 space-y-1 border-b border-slate-700">
          <button
            onClick={() => setActiveTab('discover')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-left ${
              activeTab === 'discover'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span className="font-medium">Find Products</span>
          </button>
          <button
            onClick={() => setActiveTab('search')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-left ${
              activeTab === 'search'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="font-medium">Price Search</span>
          </button>
          <button
            onClick={() => setActiveTab('shopping-list')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-left ${
              activeTab === 'shopping-list'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
            <span className="font-medium">Shopping List</span>
            {shoppingList.length > 0 && (
              <span className={`ml-auto w-5 h-5 text-xs flex items-center justify-center rounded-full ${
                activeTab === 'shopping-list' ? 'bg-cyan-500/30' : 'bg-cyan-500/20 text-cyan-400'
              }`}>
                {shoppingList.length}
              </span>
            )}
          </button>
        </nav>

        {/* History Section - context dependent */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-3">
            <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-2">
              {activeTab === 'discover' ? 'Discovery History' : activeTab === 'search' ? 'Search History' : 'Recent Searches'}
            </h3>

            {isLoadingHistory ? (
              <div className="text-center text-slate-500 py-4">
                <p className="animate-pulse text-sm">Loading...</p>
              </div>
            ) : activeTab === 'search' ? (
              // Price Search History
              searchHistory.length === 0 ? (
                <div className="text-center text-slate-500 py-4">
                  <svg className="w-8 h-8 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-xs">No search history</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {searchHistory.slice(0, 10).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => handleLocalHistoryClick(item)}
                      className="w-full text-left p-2 rounded-lg hover:bg-slate-800 transition-colors group"
                    >
                      <p className="text-sm text-white truncate">{item.query}</p>
                      <p className="text-xs text-slate-500">{formatRelativeTime(item.timestamp)}</p>
                    </button>
                  ))}
                </div>
              )
            ) : activeTab === 'discover' ? (
              // Discovery History
              discoveryHistory.length === 0 ? (
                <div className="text-center text-slate-500 py-4">
                  <svg className="w-8 h-8 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <p className="text-xs">No discovery history</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {discoveryHistory.slice(0, 10).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => handleDiscoveryHistoryClick(item)}
                      className="w-full text-left p-2 rounded-lg hover:bg-slate-800 transition-colors group"
                    >
                      <p className="text-sm text-white truncate">{item.query}</p>
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <span>{formatRelativeTime(item.timestamp)}</span>
                        {item.productCount > 0 && (
                          <>
                            <span>-</span>
                            <span>{item.productCount} products</span>
                          </>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )
            ) : (
              // Shopping List - show recent price searches
              searchHistory.length === 0 ? (
                <div className="text-center text-slate-500 py-4">
                  <svg className="w-8 h-8 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-xs">No recent price searches</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {searchHistory.slice(0, 5).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => handleLocalHistoryClick(item)}
                      className="w-full text-left p-2 rounded-lg hover:bg-slate-800 transition-colors group"
                    >
                      <p className="text-sm text-white truncate">{item.query}</p>
                      <p className="text-xs text-slate-500">{formatRelativeTime(item.timestamp)}</p>
                    </button>
                  ))}
                </div>
              )
            )}
          </div>
        </div>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-slate-700">
          <a
            href="/dashboard"
            className="flex items-center gap-2 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Dashboard
          </a>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 ml-64 min-h-screen">
        {/* Price Search Tab */}
        {activeTab === 'search' && (
          <div className="p-8">
            <div className="max-w-4xl mx-auto">
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
            {(isSearching || isLoadingTrace) && (
              <div className="text-center mt-4 space-y-2">
                <div className="text-slate-400 text-sm animate-pulse">
                  {isLoadingTrace ? 'Loading results...' : (statusMessage || 'Starting search...')}
                </div>
                {isSearching && (
                  <>
                    <div className="text-slate-500 text-xs">
                      Elapsed: {Math.floor(elapsedTime / 60)}:{(elapsedTime % 60).toString().padStart(2, '0')}
                    </div>
                    {elapsedTime > 30 && (
                      <div className="text-slate-600 text-xs">
                        Searching multiple sources - this may take a minute
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </form>

          {/* Quick suggestions */}
          {results.length === 0 && !isSearching && !isLoadingTrace && !error && !rawResultText && (
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

          {/* Recent searches (when no results) */}
          {results.length === 0 && !isSearching && !isLoadingTrace && !error && !rawResultText && searchHistory.length > 0 && (
            <div className="mt-8">
              <h3 className="text-sm text-slate-500 text-center mb-3">Recent searches</h3>
              <div className="flex flex-wrap justify-center gap-2">
                {searchHistory.slice(0, 5).map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleLocalHistoryClick(item)}
                    className="px-3 py-1.5 text-sm text-slate-500 bg-slate-800/30 rounded-lg
                             hover:bg-slate-800 hover:text-slate-300 transition-colors
                             flex items-center gap-2"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {item.query}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Results Section */}
          {(results.length > 0 || error || (rawResultText && !isSearching)) && (
            <div className="mt-8">
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
          ) : results.length > 0 ? (
            <>
              {/* Results header */}
              <div className="flex items-center justify-between mb-6">
                <div className="text-slate-400">
                  Found {results.reduce((sum, p) => sum + p.results.length, 0)} results
                  {bundles.length > 0 && ` from ${bundles.length} bundle stores`}
                  {searchTime && <span className="text-slate-600"> in {(searchTime / 1000).toFixed(1)}s</span>}
                </div>
                <a
                  href="/dashboard"
                  className="text-sm text-cyan-400 hover:underline"
                >
                  Advanced view →
                </a>
              </div>

              {/* Bundle opportunities table */}
              {bundles.length > 0 && (
                <div className="mb-8 bg-gradient-to-br from-amber-900/20 to-slate-800/50 border border-amber-500/30 rounded-xl p-4">
                  <h3 className="text-lg font-semibold text-amber-400 mb-4 flex items-center gap-2">
                    <span>Bundle Opportunities</span>
                    <span className="text-sm font-normal text-amber-400/70">
                      - Stores with multiple products
                    </span>
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-slate-400 border-b border-slate-700">
                          <th className="pb-3 font-medium w-10">Select</th>
                          <th className="pb-3 font-medium">Store</th>
                          <th className="pb-3 font-medium">Rating</th>
                          <th className="pb-3 font-medium">Products</th>
                          <th className="pb-3 font-medium">Total</th>
                          <th className="pb-3 font-medium">Contact</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bundles.map((bundle, idx) => {
                          const bundleId = `bundle-${bundle.storeName}-${idx}`;
                          const isBundleSelected = isSellerSelected(bundleId);
                          const canSelectBundle = !!bundle.contact;

                          return (
                            <tr key={idx} className={`border-b border-slate-700/50 ${isBundleSelected ? 'bg-cyan-500/10' : ''}`}>
                              <td className="py-3">
                                {canSelectBundle ? (
                                  <button
                                    onClick={() => toggleSellerSelection({
                                      id: bundleId,
                                      name: bundle.storeName,
                                      phone: bundle.contact!,
                                      price: bundle.totalPrice,
                                      productName: `Bundle (${bundle.productCount} items)`,
                                    })}
                                    className={`w-5 h-5 flex items-center justify-center rounded border-2 transition-colors
                                              ${isBundleSelected
                                                ? 'bg-cyan-500 border-cyan-500 text-white'
                                                : 'border-slate-500 hover:border-cyan-400'}`}
                                  >
                                    {isBundleSelected && (
                                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                      </svg>
                                    )}
                                  </button>
                                ) : (
                                  <span className="text-slate-500">{idx + 1}</span>
                                )}
                              </td>
                              <td className="py-3 text-white font-medium">{bundle.storeName}</td>
                            <td className="py-3">
                              {bundle.rating ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-500/20 text-amber-400 rounded text-xs">
                                  ★ {bundle.rating.toFixed(1)}
                                </span>
                              ) : '-'}
                            </td>
                            <td className="py-3">
                              <div className="space-y-1">
                                {bundle.products.map((p, pIdx) => (
                                  <div key={pIdx} className="text-xs text-slate-400">
                                    {p.name}: {p.url ? (
                                      <a href={p.url} target="_blank" rel="noopener noreferrer"
                                         className="text-cyan-400 hover:underline">
                                        ₪{p.price.toLocaleString()}
                                      </a>
                                    ) : (
                                      <span className="text-emerald-400">₪{p.price.toLocaleString()}</span>
                                    )}
                                  </div>
                                ))}
                                <div className="text-xs text-amber-400/70 italic mt-1">
                                  Ask for bundle discount
                                </div>
                              </div>
                            </td>
                            <td className="py-3">
                              <div className="text-emerald-400 font-bold">
                                ₪{bundle.totalPrice.toLocaleString()}
                              </div>
                              <div className="text-xs text-slate-500">
                                {bundle.productCount}/{bundle.totalProducts} products
                              </div>
                            </td>
                            <td className="py-3">
                              {bundle.contact ? (
                                <button
                                  onClick={() => handleContact(bundle.storeName, bundle.contact!)}
                                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/20 text-emerald-400
                                           hover:bg-emerald-500 hover:text-white rounded-lg transition-colors text-xs"
                                >
                                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
                                  </svg>
                                  Contact
                                </button>
                              ) : (
                                <span className="text-slate-500 text-xs">-</span>
                              )}
                            </td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Product sections */}
              {results.map((product, pIdx) => (
                <div key={pIdx} className="mb-8">
                  {results.length > 1 && (
                    <h2 className="text-xl font-semibold text-white mb-4">{product.productName}</h2>
                  )}

                  <div className="space-y-3">
                    {product.results.map((result, rIdx) => {
                      const sellerId = `${product.productName}-${result.seller}-${rIdx}`;
                      return (
                        <ResultCard
                          key={rIdx}
                          result={result}
                          rank={rIdx + 1}
                          productName={product.productName}
                          isSelected={isSellerSelected(sellerId)}
                          onToggleSelect={() => result.phone && toggleSellerSelection({
                            id: sellerId,
                            name: result.seller,
                            phone: result.phone,
                            price: result.price,
                            productName: product.productName,
                          })}
                          onContact={() => result.phone && handleContact(result.seller, result.phone)}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
            </>
          ) : rawResultText ? (
            // Fallback: Show raw results when parsing fails
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-slate-400">
                  Search completed
                  {searchTime && <span className="text-slate-600"> in {(searchTime / 1000).toFixed(1)}s</span>}
                </div>
                <a
                  href="/dashboard"
                  className="text-sm text-cyan-400 hover:underline"
                >
                  View in dashboard →
                </a>
              </div>

              <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                <h3 className="text-white font-medium mb-3">Agent Response</h3>
                <pre className="text-slate-300 text-sm whitespace-pre-wrap font-mono overflow-x-auto">
                  {rawResultText}
                </pre>
              </div>

              <p className="text-slate-500 text-sm text-center">
                Results displayed in raw format. View the dashboard for structured data.
              </p>
            </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    )}

    {/* Discover Tab Content */}
    {activeTab === 'discover' && (
      <div className="p-8">
        <div className="max-w-4xl mx-auto">
          <ProductDiscoveryView
            onAddToShoppingList={handleAddToShoppingList}
            country={country}
            onCountryChange={setCountry}
          />
        </div>
      </div>
    )}

    {/* Shopping List Tab Content */}
    {activeTab === 'shopping-list' && (
      <div className="p-8">
        <div className="max-w-4xl mx-auto">
          <ShoppingListView
            onSwitchToDiscover={() => setActiveTab('discover')}
            onSearchStarted={() => setActiveTab('search')}
            country={country}
          />
        </div>
      </div>
    )}
  </main>

      {/* Floating Bulk Action Bar */}
      {selectedSellers.length > 0 && (
        <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-40
                        bg-slate-800 border border-slate-600 rounded-2xl shadow-2xl
                        px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 text-white">
            <span className="w-8 h-8 flex items-center justify-center bg-cyan-500 rounded-full text-sm font-bold">
              {selectedSellers.length}
            </span>
            <span className="text-slate-300">
              {selectedSellers.length === 1 ? 'seller' : 'sellers'} selected
            </span>
          </div>

          <div className="w-px h-8 bg-slate-600" />

          <button
            onClick={sendBulkWhatsApp}
            disabled={isGeneratingDrafts}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-400
                     disabled:bg-emerald-500/50 disabled:cursor-wait
                     text-white font-medium rounded-xl transition-colors"
          >
            {isGeneratingDrafts ? (
              <>
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Generating Messages...
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
                </svg>
                Contact Sellers
              </>
            )}
          </button>

          <button
            onClick={clearSelection}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700
                     rounded-lg transition-colors"
            title="Clear selection"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Footer - Subtle branding */}
      <footer className="fixed bottom-0 left-64 right-0 py-3 text-center text-xs text-slate-600">
        <span>Powered by Claude AI</span>
      </footer>

      {/* Draft Modal for bulk messaging */}
      <DraftModal />

      {/* Price Search Notification */}
      <PriceSearchNotification
        onViewResults={(traceId) => {
          router.push(`/dashboard?trace=${traceId}`);
        }}
      />
    </div>
  );
}

// Result Card Component
function ResultCard({
  result,
  rank,
  productName,
  isSelected,
  onToggleSelect,
  onContact,
}: {
  result: SearchResult;
  rank: number;
  productName: string;
  isSelected: boolean;
  onToggleSelect: () => void;
  onContact: () => void;
}) {
  const formatPrice = (price: number, currency: string) => {
    if (currency === 'ILS') {
      return `₪${price.toLocaleString()}`;
    }
    return `${currency} ${price.toLocaleString()}`;
  };

  const canSelect = !!result.phone;

  return (
    <div className={`group bg-slate-800/50 border rounded-xl p-4 transition-all duration-300
                    ${isSelected ? 'border-cyan-500 bg-cyan-500/10' : 'border-slate-700/50 hover:border-cyan-500/30 hover:bg-slate-800/70'}`}>
      <div className="flex items-start justify-between gap-4">
        {/* Left: Checkbox and Seller info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3">
            {/* Checkbox - only show if has phone */}
            {canSelect ? (
              <button
                onClick={onToggleSelect}
                className={`flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-md border-2 transition-colors
                          ${isSelected
                            ? 'bg-cyan-500 border-cyan-500 text-white'
                            : 'border-slate-500 hover:border-cyan-400'}`}
              >
                {isSelected && (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </button>
            ) : (
              <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center
                             bg-slate-700 rounded-full text-xs text-slate-400">
                {rank}
              </span>
            )}
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
  const allResults: ProductResult[] = [];

  // Debug: log what we're parsing
  console.log('[Parser] Parsing text:', text.substring(0, 500));

  // Check if this is a multi-product result with sections
  const sectionPattern = /\n=== ([^=\n]+) ===\n/g;
  const sections: Array<{ name: string; startIndex: number }> = [];
  let match;

  while ((match = sectionPattern.exec(text)) !== null) {
    if (!match[1].includes('BUNDLE')) {
      sections.push({ name: match[1].trim(), startIndex: match.index + match[0].length });
    }
  }

  if (sections.length > 0) {
    // Multi-product format with sections
    for (let i = 0; i < sections.length; i++) {
      const startIdx = sections[i].startIndex;
      const endIdx = i + 1 < sections.length
        ? text.indexOf('\n===', startIdx)
        : text.length;

      const sectionText = text.slice(startIdx, endIdx > 0 ? endIdx : undefined);
      const results = parseResultsSection(sectionText);

      if (results.length > 0) {
        allResults.push({
          productName: sections[i].name,
          results,
        });
      }
    }
  } else {
    // Single product format - parse entire text
    const results = parseResultsSection(text);
    if (results.length > 0) {
      allResults.push({
        productName: 'Search Results',
        results,
      });
    }
  }

  console.log('[Parser] Parsed results:', allResults.length, 'products');
  return allResults;
}

// Parse a single section of results
function parseResultsSection(text: string): SearchResult[] {
  const results: SearchResult[] = [];
  const lines = text.split('\n');

  console.log('[Parser] Parsing section with', lines.length, 'lines');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmedLine = line.trim();

    // Match numbered lines like: "1. Seller Name" or "1. Seller (Rating: 4.5/5) [source]"
    // Use a simpler pattern first, then extract parts
    const numberedMatch = trimmedLine.match(/^(\d+)\.\s+(.+)/);

    if (numberedMatch) {
      const rest = numberedMatch[2];
      console.log('[Parser] Found numbered line:', numberedMatch[1], '-', rest);

      // Extract seller name, rating, and source from the rest
      let seller = rest;
      let rating: number | undefined;
      let source: string | undefined;

      // Extract [source] from end if present
      const sourceMatch = rest.match(/\[([^\]]+)\]\s*$/);
      if (sourceMatch) {
        source = sourceMatch[1];
        seller = rest.slice(0, rest.lastIndexOf('[')).trim();
      }

      // Extract (Rating: X/5) if present
      const ratingMatch = seller.match(/\(Rating:\s*([\d.]+)\/5\)\s*$/);
      if (ratingMatch) {
        rating = parseFloat(ratingMatch[1]);
        seller = seller.slice(0, seller.lastIndexOf('(')).trim();
      }

      console.log('[Parser] Extracted - seller:', seller, 'rating:', rating, 'source:', source);

      // Look for price, URL, contact in following lines
      let price = 0;
      let currency = 'ILS';
      let url: string | undefined;
      let phone: string | undefined;

      // Parse following lines for details (up to 6 lines or until next numbered item)
      for (let j = i + 1; j < Math.min(i + 7, lines.length); j++) {
        const detailLine = lines[j].trim();

        // Stop if we hit another numbered result
        if (/^\d+\.\s/.test(detailLine)) break;

        // Match price in various formats
        const priceMatch = detailLine.match(/Price:\s*([\d,]+(?:\.\d+)?)\s*(\w+)?/i);
        if (priceMatch) {
          price = parseFloat(priceMatch[1].replace(/,/g, ''));
          currency = priceMatch[2] || 'ILS';
          console.log('[Parser] Found price:', price, currency);
        }

        // Match URL
        const urlMatch = detailLine.match(/URL:\s*(https?:\/\/[^\s]+)/i);
        if (urlMatch) {
          url = urlMatch[1];
        }

        // Match contact/phone
        const contactMatch = detailLine.match(/Contact:\s*(\+?[\d\s-]+)/i);
        if (contactMatch) {
          phone = contactMatch[1].replace(/[\s-]/g, '');
        }
      }

      // Only add if we found a price
      if (price > 0) {
        results.push({
          seller,
          price,
          currency,
          rating,
          url,
          phone,
          source,
        });
        console.log('[Parser] Added result:', seller, price);
      } else {
        console.log('[Parser] Skipped (no price):', seller);
      }
    }
  }

  console.log('[Parser] Section results:', results.length);
  return results;
}

// Parse search tool output format (same as dashboard)
// Format: "1. Seller Name (Rating: X/5)\n   Price: X,XXX ILS\n   URL: https://...\n   Contact: +972..."
function parseToolOutput(text: string): SearchResult[] {
  const results: SearchResult[] = [];

  // Split by numbered items (1. 2. 3. etc)
  const itemPattern = /(?:^|\n)(\d+)\.\s+([^\n]+)/g;
  let match;

  while ((match = itemPattern.exec(text)) !== null) {
    const sellerLine = match[2];

    // Extract seller name and rating from the seller line
    // Format: "Seller Name (Rating: 4.5/5)"
    const ratingMatch = sellerLine.match(/(.+?)\s*\(Rating:\s*([\d.]+)\/5\)/);
    let seller: string;
    let rating: number | undefined;

    if (ratingMatch) {
      seller = ratingMatch[1].trim();
      rating = parseFloat(ratingMatch[2]);
    } else {
      seller = sellerLine.trim();
    }

    // Get the text after this match until the next numbered item or end
    const startPos = match.index + match[0].length;
    const nextMatch = text.slice(startPos).match(/\n\d+\./);
    const endPos = nextMatch && nextMatch.index !== undefined ? startPos + nextMatch.index : text.length;
    const detailsText = text.slice(startPos, endPos);

    // Extract price
    const priceMatch = detailsText.match(/Price:\s*([\d,]+)/i);
    const price = priceMatch ? parseInt(priceMatch[1].replace(/,/g, ''), 10) : 0;

    // Extract currency
    const currencyMatch = detailsText.match(/Price:\s*[\d,]+\s*(\w+)/i);
    const currency = currencyMatch ? currencyMatch[1] : 'ILS';

    // Extract URL
    const urlMatch = detailsText.match(/URL:\s*(https?:\/\/[^\s\n]+)/i);
    const url = urlMatch ? urlMatch[1] : undefined;

    // Extract phone/contact
    const phoneMatch = detailsText.match(/(?:Contact|Phone|WhatsApp):\s*(\+?[\d\s-]+)/i);
    const phone = phoneMatch ? phoneMatch[1].replace(/[\s-]/g, '') : undefined;

    if (price > 0) {
      results.push({
        seller,
        price,
        currency,
        rating,
        url,
        phone,
      });
    }
  }

  return results;
}

// Parse bundle opportunities section from multi-product search
function parseBundleSection(text: string): BundleResult[] {
  const bundles: BundleResult[] = [];

  // Check for bundle section
  const bundleMatch = text.match(/=== BUNDLE OPPORTUNITIES \((\d+) stores\) ===/);
  if (!bundleMatch) return [];

  // Get just the bundle section (up to the next === section or end)
  const bundleStart = text.indexOf('=== BUNDLE OPPORTUNITIES');
  const nextSection = text.slice(bundleStart + 30).match(/\n===\s+[^B]/);
  const bundleEnd = nextSection ? bundleStart + 30 + nextSection.index! : text.length;
  const bundleText = text.slice(bundleStart, bundleEnd);

  // Parse each store entry
  const storePattern = /(\d+)\.\s+([^\n]+?)(?:\s+\(Rating:\s*([\d.]+)\/5\))?\n([\s\S]*?)(?=\n\d+\.|$)/g;
  let match;

  while ((match = storePattern.exec(bundleText)) !== null) {
    const storeName = match[2].trim();
    const rating = match[3] ? parseFloat(match[3]) : undefined;
    const details = match[4];

    // Extract product count
    const offersMatch = details.match(/Offers\s+(\d+)\/(\d+)\s+products/);
    const productCount = offersMatch ? parseInt(offersMatch[1]) : 0;
    const totalProducts = offersMatch ? parseInt(offersMatch[2]) : 0;

    // Extract product lines: "- Query: X,XXX ILS | URL"
    const products: BundleResult['products'] = [];
    const productPattern = /^\s+-\s+([^:]+):\s+([\d,]+)\s+(\w+)(?:\s*\|\s*(https?:\/\/[^\s]+))?/gm;
    let productMatch;
    while ((productMatch = productPattern.exec(details)) !== null) {
      products.push({
        name: productMatch[1].trim(),
        price: parseInt(productMatch[2].replace(/,/g, ''), 10),
        currency: productMatch[3],
        url: productMatch[4] || undefined,
      });
    }

    // Extract total price
    const totalMatch = details.match(/Total:\s+([\d,]+)/);
    const totalPrice = totalMatch ? parseInt(totalMatch[1].replace(/,/g, ''), 10) : 0;

    // Extract contact
    const contactMatch = details.match(/Contact:\s*(\+?[\d\s-]+)/);
    const contact = contactMatch ? contactMatch[1].replace(/[\s-]/g, '') : undefined;

    if (totalPrice > 0) {
      bundles.push({
        storeName,
        rating,
        productCount,
        totalProducts,
        products,
        totalPrice,
        contact,
      });
    }
  }

  return bundles;
}
