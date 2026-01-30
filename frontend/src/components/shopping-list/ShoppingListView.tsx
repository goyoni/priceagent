/**
 * ShoppingListView component for managing the shopping list.
 */

'use client';

import { useState, useCallback } from 'react';
import { useShoppingListStore } from '@/stores/useShoppingListStore';
import { ShoppingListItem } from './ShoppingListItem';

interface ShoppingListViewProps {
  onSwitchToDiscover: () => void;
  country: string;
}

export function ShoppingListView({ onSwitchToDiscover, country }: ShoppingListViewProps) {
  const { items, removeItem, clearList, addItem, startPriceSearch, isSearching } = useShoppingListStore();

  const [isAddingManual, setIsAddingManual] = useState(false);
  const [manualProduct, setManualProduct] = useState('');
  const [manualModel, setManualModel] = useState('');
  const [searchError, setSearchError] = useState<string | null>(null);

  const handleAddManual = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!manualProduct.trim()) return;

    addItem({
      product_name: manualProduct.trim(),
      model_number: manualModel.trim() || undefined,
      source: 'manual',
    });

    setManualProduct('');
    setManualModel('');
    setIsAddingManual(false);
  }, [manualProduct, manualModel, addItem]);

  const handleClearList = useCallback(() => {
    if (window.confirm('Are you sure you want to clear your entire shopping list?')) {
      clearList();
    }
  }, [clearList]);

  const handleStartSearch = useCallback(async () => {
    setSearchError(null);
    try {
      await startPriceSearch(country);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to start search');
    }
  }, [startPriceSearch, country]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-semibold text-white">Shopping List</h2>
            <p className="text-slate-400 text-sm mt-1">
              {items.length === 0
                ? 'Add products to compare prices'
                : `${items.length} item${items.length !== 1 ? 's' : ''} in your list`}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsAddingManual(!isAddingManual)}
              className="px-3 py-1.5 text-sm bg-slate-700 text-slate-300 hover:bg-slate-600
                       rounded-lg transition-colors flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                />
              </svg>
              Add Manually
            </button>

            {items.length > 0 && (
              <button
                onClick={handleClearList}
                className="px-3 py-1.5 text-sm text-slate-500 hover:text-red-400
                         transition-colors"
              >
                Clear All
              </button>
            )}
          </div>
        </div>

        {/* Manual Add Form */}
        {isAddingManual && (
          <form onSubmit={handleAddManual} className="mt-4 p-4 bg-slate-900/50 rounded-lg space-y-3">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Product Name *</label>
              <input
                type="text"
                value={manualProduct}
                onChange={(e) => setManualProduct(e.target.value)}
                placeholder="e.g., Samsung Refrigerator"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg
                         text-white placeholder-slate-500 outline-none
                         focus:border-cyan-500 transition-colors"
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Model Number (optional)</label>
              <input
                type="text"
                value={manualModel}
                onChange={(e) => setManualModel(e.target.value)}
                placeholder="e.g., RF72DG9620B1"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg
                         text-white placeholder-slate-500 outline-none
                         focus:border-cyan-500 transition-colors"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsAddingManual(false)}
                className="px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!manualProduct.trim()}
                className="px-4 py-1.5 text-sm bg-cyan-500 text-white rounded-lg
                         hover:bg-cyan-400 disabled:bg-slate-600 disabled:text-slate-400
                         transition-colors"
              >
                Add to List
              </button>
            </div>
          </form>
        )}
      </div>

      {/* List Items */}
      {items.length === 0 ? (
        <div className="bg-slate-800/30 border border-slate-700 rounded-xl p-12 text-center">
          <svg
            className="w-16 h-16 mx-auto text-slate-600 mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            />
          </svg>
          <p className="text-slate-400 mb-2">Your shopping list is empty</p>
          <p className="text-slate-500 text-sm mb-4">
            Use "Find Products" to discover products with AI, or add items manually
          </p>
          <button
            onClick={onSwitchToDiscover}
            className="px-4 py-2 bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500 hover:text-white
                     rounded-lg transition-colors text-sm"
          >
            Find Products with AI
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <ShoppingListItem
              key={item.id}
              item={item}
              onRemove={removeItem}
            />
          ))}

          {/* Price Search Button */}
          <div className="pt-4 border-t border-slate-700">
            {searchError && (
              <div className="mb-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                {searchError}
              </div>
            )}
            <button
              onClick={handleStartSearch}
              disabled={isSearching}
              className={`w-full py-3 bg-gradient-to-r from-emerald-500 to-teal-500
                       text-white font-medium rounded-xl
                       flex items-center justify-center gap-2 transition-all
                       ${isSearching ? 'opacity-75 cursor-wait' : 'hover:from-emerald-400 hover:to-teal-400'}`}
            >
              {isSearching ? (
                <>
                  <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24">
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
                  Searching prices...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                  Search Prices for All Items
                </>
              )}
            </button>
            <p className="text-center text-slate-500 text-xs mt-2">
              {isSearching
                ? 'You can continue browsing while we search'
                : 'We\'ll search all your items at once and notify you when done'}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
