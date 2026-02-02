/**
 * Search history management using localStorage.
 * Each user's browser stores their own search history.
 */

export type SearchStatus = 'searching' | 'completed' | 'error';

export interface SearchHistoryItem {
  id: string;
  query: string;
  timestamp: number;
  resultCount: number;
  searchTimeMs: number;
  traceId?: string;  // Store trace ID for URL sharing
  status: SearchStatus;
  error?: string;
  // Store a summary of results for quick display
  topResults?: Array<{
    seller: string;
    price: number;
    currency: string;
  }>;
}

const STORAGE_KEY = 'shoppingagent_search_history';
const OLD_STORAGE_KEY = 'priceagent_search_history';
const MAX_HISTORY_ITEMS = 50;

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
      console.log('[SearchHistory] Migrating from old storage key');
      localStorage.setItem(STORAGE_KEY, oldData);
      localStorage.removeItem(OLD_STORAGE_KEY);
    }
  } catch (error) {
    console.error('[SearchHistory] Migration failed:', error);
  }
}

// Run migration on module load
migrateFromOldKey();

/**
 * Get all search history items, sorted by most recent first.
 */
export function getSearchHistory(): SearchHistoryItem[] {
  if (typeof window === 'undefined') return [];

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];

    const items = JSON.parse(stored) as SearchHistoryItem[];
    // Migrate old items without status field - default to 'completed'
    const migratedItems = items.map(item => ({
      ...item,
      status: item.status || 'completed' as SearchStatus,
    }));
    // Sort by timestamp descending (most recent first)
    return migratedItems.sort((a, b) => b.timestamp - a.timestamp);
  } catch (error) {
    console.error('[SearchHistory] Failed to load:', error);
    return [];
  }
}

/**
 * Add a new search to history.
 */
export function addToSearchHistory(item: Omit<SearchHistoryItem, 'id'>): SearchHistoryItem {
  const history = getSearchHistory();

  const newItem: SearchHistoryItem = {
    ...item,
    id: `search_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
  };

  // Add to beginning of array
  history.unshift(newItem);

  // Limit to max items
  const trimmed = history.slice(0, MAX_HISTORY_ITEMS);

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (error) {
    console.error('[SearchHistory] Failed to save:', error);
  }

  return newItem;
}

/**
 * Update an existing search history item by traceId.
 */
export function updateSearchHistoryByTraceId(
  traceId: string,
  updates: Partial<Pick<SearchHistoryItem, 'resultCount' | 'status' | 'error' | 'topResults' | 'searchTimeMs'>>
): SearchHistoryItem | null {
  const history = getSearchHistory();
  const index = history.findIndex(h => h.traceId === traceId);

  if (index === -1) {
    console.warn('[SearchHistory] Item not found for traceId:', traceId);
    return null;
  }

  const item = history[index];
  if (updates.resultCount !== undefined) item.resultCount = updates.resultCount;
  if (updates.status !== undefined) item.status = updates.status;
  if (updates.error !== undefined) item.error = updates.error;
  if (updates.topResults !== undefined) item.topResults = updates.topResults;
  if (updates.searchTimeMs !== undefined) item.searchTimeMs = updates.searchTimeMs;

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (error) {
    console.error('[SearchHistory] Failed to update:', error);
  }

  return item;
}

/**
 * Get a specific search by ID.
 */
export function getSearchById(id: string): SearchHistoryItem | undefined {
  const history = getSearchHistory();
  return history.find(item => item.id === id);
}

/**
 * Delete a search from history.
 */
export function deleteFromHistory(id: string): void {
  const history = getSearchHistory();
  const filtered = history.filter(item => item.id !== id);

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error('[SearchHistory] Failed to delete:', error);
  }
}

/**
 * Clear all search history.
 */
export function clearSearchHistory(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('[SearchHistory] Failed to clear:', error);
  }
}

/**
 * Format a timestamp as a relative time string.
 */
export function formatRelativeTime(timestamp: number): string {
  const now = Date.now();
  const diff = now - timestamp;

  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;

  // Format as date for older items
  return new Date(timestamp).toLocaleDateString();
}
