/**
 * GroupedProductsView component for displaying products grouped by type.
 * Used for multi-product searches to show products organized by category.
 */

'use client';

import type { DiscoveredProduct } from '@/lib/types';

interface GroupedProductsViewProps {
  productsByType: Record<string, DiscoveredProduct[]>;
  onAddToList: (product: DiscoveredProduct) => void;
  isAddingId?: string;
}

export function GroupedProductsView({
  productsByType,
  onAddToList,
  isAddingId,
}: GroupedProductsViewProps) {
  const productTypes = Object.keys(productsByType);

  if (productTypes.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No products found.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {productTypes.map((productType) => (
        <ProductTypeSection
          key={productType}
          productType={productType}
          products={productsByType[productType]}
          onAddToList={onAddToList}
          isAddingId={isAddingId}
        />
      ))}
    </div>
  );
}

interface ProductTypeSectionProps {
  productType: string;
  products: DiscoveredProduct[];
  onAddToList: (product: DiscoveredProduct) => void;
  isAddingId?: string;
}

function ProductTypeSection({
  productType,
  products,
  onAddToList,
  isAddingId,
}: ProductTypeSectionProps) {
  // Format product type for display (snake_case to Title Case)
  const displayName = productType
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
      {/* Section header */}
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <h4 className="font-semibold text-gray-800">{displayName}</h4>
        <span className="text-sm text-gray-500">{products.length} products</span>
      </div>

      {/* Products grid */}
      <div className="p-4">
        <div className="grid gap-3">
          {products.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              onAddToList={onAddToList}
              isAdding={isAddingId === product.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface ProductCardProps {
  product: DiscoveredProduct;
  onAddToList: (product: DiscoveredProduct) => void;
  isAdding: boolean;
}

function ProductCard({
  product,
  onAddToList,
  isAdding,
}: ProductCardProps) {
  // Extract matching attributes if available
  const matchingAttrs = (product as { matching_attributes?: Record<string, string> }).matching_attributes;
  const hasMatches = (product as { has_matches?: boolean }).has_matches;

  return (
    <div className={`
      flex items-center justify-between gap-4 p-3 rounded-lg border
      ${hasMatches ? 'border-emerald-200 bg-emerald-50/30' : 'border-gray-100 bg-gray-50/30'}
    `}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-800 truncate">{product.name}</span>
          {hasMatches && (
            <span className="text-xs px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded">
              Has matches
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 mt-1">
          {product.brand && (
            <span className="text-xs text-gray-500">{product.brand}</span>
          )}
          {product.model_number && (
            <span className="text-xs font-mono text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">
              {product.model_number}
            </span>
          )}
        </div>

        {/* Matching attributes */}
        {matchingAttrs && Object.keys(matchingAttrs).length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {Object.entries(matchingAttrs).map(([key, value]) => (
              <span
                key={key}
                className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded"
                title={`${key}: ${value}`}
              >
                {value}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* Price */}
        {(product.price || product.price_range) && (
          <div className="text-right whitespace-nowrap">
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
            disabled={isAdding}
            className="px-2 py-1 text-xs font-medium
                       bg-indigo-50 text-indigo-600
                       hover:bg-indigo-500 hover:text-white
                       disabled:opacity-50 disabled:cursor-wait
                       rounded transition-colors"
          >
            {isAdding ? '...' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
}
