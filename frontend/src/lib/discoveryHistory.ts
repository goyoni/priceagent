/**
 * Discovery history management using localStorage.
 * Stores user's product discovery searches separately from price searches.
 */

export type DiscoveryStatus = 'searching' | 'completed' | 'error';

export interface DiscoveryHistoryItem {
  id: string;
  query: string;
  timestamp: number;
  productCount: number;
  traceId?: string;
  status: DiscoveryStatus;
  error?: string;
}

const STORAGE_KEY = 'shoppingagent_discovery_history';
const MAX_HISTORY_ITEMS = 50;

/**
 * Get all discovery history items, sorted by most recent first.
 */
export function getDiscoveryHistory(): DiscoveryHistoryItem[] {
  if (typeof window === 'undefined') return [];

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];

    const items = JSON.parse(stored) as DiscoveryHistoryItem[];
    // Migrate old items without status field - default to 'completed'
    const migratedItems = items.map(item => ({
      ...item,
      status: item.status || 'completed' as DiscoveryStatus,
    }));
    // Sort by timestamp descending (most recent first)
    return migratedItems.sort((a, b) => b.timestamp - a.timestamp);
  } catch (error) {
    console.error('[DiscoveryHistory] Failed to load:', error);
    return [];
  }
}

/**
 * Add a new discovery to history.
 * Prevents duplicates by traceId.
 */
export function addToDiscoveryHistory(item: Omit<DiscoveryHistoryItem, 'id'>): DiscoveryHistoryItem {
  const history = getDiscoveryHistory();

  // Prevent duplicates by traceId
  if (item.traceId) {
    const existingIndex = history.findIndex(h => h.traceId === item.traceId);
    if (existingIndex !== -1) {
      // Update existing entry instead of adding duplicate
      const existing = history[existingIndex];
      existing.productCount = item.productCount;
      existing.timestamp = item.timestamp;
      existing.status = item.status;
      if (item.error) existing.error = item.error;
      history.splice(existingIndex, 1);
      history.unshift(existing);

      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
      } catch (error) {
        console.error('[DiscoveryHistory] Failed to save:', error);
      }

      return existing;
    }
  }

  const newItem: DiscoveryHistoryItem = {
    ...item,
    id: `discovery_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
  };

  // Add to beginning of array
  history.unshift(newItem);

  // Limit to max items
  const trimmed = history.slice(0, MAX_HISTORY_ITEMS);

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (error) {
    console.error('[DiscoveryHistory] Failed to save:', error);
  }

  return newItem;
}

/**
 * Update an existing discovery history item by traceId.
 */
export function updateDiscoveryHistoryByTraceId(
  traceId: string,
  updates: Partial<Pick<DiscoveryHistoryItem, 'productCount' | 'status' | 'error'>>
): DiscoveryHistoryItem | null {
  const history = getDiscoveryHistory();
  const index = history.findIndex(h => h.traceId === traceId);

  if (index === -1) {
    console.warn('[DiscoveryHistory] Item not found for traceId:', traceId);
    return null;
  }

  const item = history[index];
  if (updates.productCount !== undefined) item.productCount = updates.productCount;
  if (updates.status !== undefined) item.status = updates.status;
  if (updates.error !== undefined) item.error = updates.error;

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (error) {
    console.error('[DiscoveryHistory] Failed to update:', error);
  }

  return item;
}

/**
 * Get a specific discovery by ID.
 */
export function getDiscoveryById(id: string): DiscoveryHistoryItem | undefined {
  const history = getDiscoveryHistory();
  return history.find(item => item.id === id);
}

/**
 * Delete a discovery from history.
 */
export function deleteFromDiscoveryHistory(id: string): void {
  const history = getDiscoveryHistory();
  const filtered = history.filter(item => item.id !== id);

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error('[DiscoveryHistory] Failed to delete:', error);
  }
}

/**
 * Clear all discovery history.
 */
export function clearDiscoveryHistory(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('[DiscoveryHistory] Failed to clear:', error);
  }
}
