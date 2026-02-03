/**
 * MatchedSetsView component for displaying matched product sets.
 * Shows pairs/groups of products that match in color, style, or brand.
 */

'use client';

import type { DiscoveredProduct, ProductMatch } from '@/lib/types';

interface MatchedSetsViewProps {
  matchedSets: ProductMatch[];
  onAddToList: (product: DiscoveredProduct) => void;
  isAddingId?: string;
}

export function MatchedSetsView({
  matchedSets,
  onAddToList,
  isAddingId,
}: MatchedSetsViewProps) {
  if (!matchedSets || matchedSets.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <p>No matching product sets found.</p>
        <p className="text-sm mt-2">Try searching for products with similar colors, styles, or brands.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-gray-800">
        Matched Sets ({matchedSets.length})
      </h3>

      <div className="grid gap-6">
        {matchedSets.map((set, index) => (
          <MatchedSetCard
            key={set.set_id}
            set={set}
            index={index + 1}
            onAddToList={onAddToList}
            isAddingId={isAddingId}
          />
        ))}
      </div>
    </div>
  );
}

interface MatchedSetCardProps {
  set: ProductMatch;
  index: number;
  onAddToList: (product: DiscoveredProduct) => void;
  isAddingId?: string;
}

function MatchedSetCard({
  set,
  index,
  onAddToList,
  isAddingId,
}: MatchedSetCardProps) {
  const matchScorePercent = Math.round(set.match_score * 100);

  // Determine match score color
  const scoreColor = matchScorePercent >= 70
    ? 'text-emerald-600 bg-emerald-50'
    : matchScorePercent >= 50
    ? 'text-amber-600 bg-amber-50'
    : 'text-gray-600 bg-gray-100';

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
      {/* Header */}
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-gray-500">Set #{index}</span>
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${scoreColor}`}>
            {matchScorePercent}% match
          </span>
        </div>
        {set.combined_price && (
          <div className="text-sm">
            <span className="text-gray-500">Combined: </span>
            <span className="font-semibold text-emerald-600">
              {set.currency === 'ILS' ? '₪' : set.currency}
              {set.combined_price.toLocaleString()}
            </span>
          </div>
        )}
      </div>

      {/* Match reasons */}
      {set.match_reasons.length > 0 && (
        <div className="px-4 py-2 bg-indigo-50/50 border-b border-gray-200">
          <div className="flex flex-wrap gap-2">
            {set.match_reasons.map((reason, i) => (
              <span
                key={i}
                className="text-xs px-2 py-1 bg-indigo-100 text-indigo-700 rounded"
              >
                {reason}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Products */}
      <div className="divide-y divide-gray-100">
        {set.products.map((product, productIndex) => (
          <div key={product.id} className="px-4 py-3 flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 uppercase tracking-wide">
                  {set.product_types?.[productIndex]?.replace(/_/g, ' ') || `Product ${productIndex + 1}`}
                </span>
              </div>
              <div className="font-medium text-gray-800 truncate">{product.name}</div>
              {product.model_number && (
                <div className="text-xs font-mono text-indigo-600 mt-0.5">
                  {product.model_number}
                </div>
              )}
              {product.brand && (
                <div className="text-xs text-gray-500 mt-0.5">
                  {product.brand}
                </div>
              )}
            </div>

            <div className="flex items-center gap-4">
              {/* Price */}
              {(product.price || product.price_range) && (
                <div className="text-right">
                  <span className="text-emerald-600 font-medium">
                    {product.price_range || (
                      <>
                        {product.currency === 'ILS' ? '₪' : product.currency}
                        {product.price?.toLocaleString()}
                      </>
                    )}
                  </span>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                {product.url ? (
                  <a
                    href={product.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                  >
                    View
                  </a>
                ) : (
                  <a
                    href={`https://www.google.com/search?q=${encodeURIComponent((product.brand ? product.brand + ' ' : '') + (product.model_number || product.name))}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                  >
                    Search
                  </a>
                )}
                <button
                  onClick={() => onAddToList(product)}
                  disabled={isAddingId === product.id}
                  className="px-2 py-1 text-xs font-medium
                             bg-indigo-50 text-indigo-600
                             hover:bg-indigo-500 hover:text-white
                             disabled:opacity-50 disabled:cursor-wait
                             rounded transition-colors"
                >
                  {isAddingId === product.id ? '...' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
