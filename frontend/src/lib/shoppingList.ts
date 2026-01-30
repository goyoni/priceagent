/**
 * Shopping list management using localStorage.
 * Follows the same pattern as searchHistory.ts.
 */

import type { ShoppingListItem } from './types';

const STORAGE_KEY = 'priceagent_shopping_list';
const MAX_LIST_ITEMS = 100;

/**
 * Get all shopping list items, sorted by most recently added first.
 */
export function getShoppingList(): ShoppingListItem[] {
  if (typeof window === 'undefined') return [];

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];

    const items = JSON.parse(stored) as ShoppingListItem[];
    // Sort by added_at descending (most recent first)
    return items.sort((a, b) =>
      new Date(b.added_at).getTime() - new Date(a.added_at).getTime()
    );
  } catch (error) {
    console.error('[ShoppingList] Failed to load:', error);
    return [];
  }
}

/**
 * Add a new item to the shopping list.
 */
export function addToShoppingList(
  item: Omit<ShoppingListItem, 'id' | 'added_at'>
): ShoppingListItem {
  const list = getShoppingList();

  const newItem: ShoppingListItem = {
    ...item,
    id: `item_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
    added_at: new Date().toISOString(),
  };

  // Add to beginning of array
  list.unshift(newItem);

  // Limit to max items
  const trimmed = list.slice(0, MAX_LIST_ITEMS);

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (error) {
    console.error('[ShoppingList] Failed to save:', error);
  }

  return newItem;
}

/**
 * Update an existing item in the shopping list.
 */
export function updateShoppingListItem(
  id: string,
  updates: Partial<Omit<ShoppingListItem, 'id' | 'added_at'>>
): ShoppingListItem | undefined {
  const list = getShoppingList();
  const index = list.findIndex(item => item.id === id);

  if (index === -1) return undefined;

  const updatedItem = { ...list[index], ...updates };
  list[index] = updatedItem;

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch (error) {
    console.error('[ShoppingList] Failed to update:', error);
  }

  return updatedItem;
}

/**
 * Remove an item from the shopping list.
 */
export function removeFromShoppingList(id: string): void {
  const list = getShoppingList();
  const filtered = list.filter(item => item.id !== id);

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error('[ShoppingList] Failed to remove:', error);
  }
}

/**
 * Clear the entire shopping list.
 */
export function clearShoppingList(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('[ShoppingList] Failed to clear:', error);
  }
}

/**
 * Get a specific item by ID.
 */
export function getShoppingListItem(id: string): ShoppingListItem | undefined {
  const list = getShoppingList();
  return list.find(item => item.id === id);
}

/**
 * Check if an item with the same model number already exists.
 */
export function isDuplicateItem(modelNumber: string): boolean {
  if (!modelNumber) return false;
  const list = getShoppingList();
  return list.some(item =>
    item.model_number?.toLowerCase() === modelNumber.toLowerCase()
  );
}

/**
 * Format relative time for display.
 */
export function formatAddedTime(addedAt: string): string {
  const timestamp = new Date(addedAt).getTime();
  const now = Date.now();
  const diff = now - timestamp;

  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;

  return new Date(timestamp).toLocaleDateString();
}
