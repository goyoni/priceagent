/**
 * DiscoveryResultsTable component for displaying discovered products.
 * Shows products in a comparison table with specs as columns.
 */

'use client';

import { useMemo } from 'react';
import type { DiscoveredProduct } from '@/lib/types';

interface DiscoveryResultsTableProps {
  products: DiscoveredProduct[];
  onAddToList: (product: DiscoveredProduct) => void;
  isAddingId?: string;
}

/**
 * Parse a spec string like "Volume: 65L" into { key: "Volume", value: "65L" }
 */
function parseSpec(spec: string): { key: string; value: string } | null {
  const colonIndex = spec.indexOf(':');
  if (colonIndex === -1) {
    // No colon, treat whole string as value with empty key
    return null;
  }
  const key = spec.substring(0, colonIndex).trim();
  const value = spec.substring(colonIndex + 1).trim();
  return { key, value };
}

/**
 * Extract all unique spec keys from products, maintaining order of first appearance.
 */
function extractSpecColumns(products: DiscoveredProduct[]): string[] {
  const seenKeys = new Set<string>();
  const orderedKeys: string[] = [];

  for (const product of products) {
    for (const spec of product.key_specs) {
      const parsed = parseSpec(spec);
      if (parsed && !seenKeys.has(parsed.key)) {
        seenKeys.add(parsed.key);
        orderedKeys.push(parsed.key);
      }
    }
  }

  return orderedKeys;
}

/**
 * Build a map of spec key -> value for a product.
 */
function buildSpecMap(product: DiscoveredProduct): Record<string, string> {
  const map: Record<string, string> = {};
  for (const spec of product.key_specs) {
    const parsed = parseSpec(spec);
    if (parsed) {
      map[parsed.key] = parsed.value;
    }
  }
  return map;
}

export function DiscoveryResultsTable({
  products,
  onAddToList,
  isAddingId,
}: DiscoveryResultsTableProps) {
  // Extract spec columns from all products
  const specColumns = useMemo(() => extractSpecColumns(products), [products]);

  // Build spec maps for each product
  const productSpecMaps = useMemo(
    () => products.map((p) => buildSpecMap(p)),
    [products]
  );

  if (!products || products.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-800">
        Recommended Products ({products.length})
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b-2 border-gray-200 text-left text-gray-600 bg-gray-50">
              <th className="px-3 py-3 font-semibold sticky left-0 bg-gray-50">#</th>
              <th className="px-3 py-3 font-semibold min-w-[200px]">Product</th>
              <th className="px-3 py-3 font-semibold">Brand</th>
              {specColumns.map((col) => (
                <th key={col} className="px-3 py-3 font-semibold whitespace-nowrap">
                  {col}
                </th>
              ))}
              <th className="px-3 py-3 font-semibold">Price</th>
              <th className="px-3 py-3 font-semibold min-w-[150px]">Why Recommended</th>
              <th className="px-3 py-3 font-semibold text-center">Action</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product, index) => (
              <tr
                key={product.id}
                className="border-b border-gray-200/50 hover:bg-indigo-50/30 transition-colors"
              >
                {/* Index */}
                <td className="px-3 py-3 text-gray-400 sticky left-0 bg-white">
                  {index + 1}
                </td>

                {/* Product name & model */}
                <td className="px-3 py-3">
                  <div className="font-medium text-gray-800">{product.name}</div>
                  {product.model_number && (
                    <div className="text-xs font-mono text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded inline-block mt-1">
                      {product.model_number}
                    </div>
                  )}
                  <div className="mt-1">
                    {product.url ? (
                      <a
                        href={product.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-indigo-600 hover:underline"
                      >
                        View product →
                      </a>
                    ) : (
                      <a
                        href={`https://www.google.com/search?q=${encodeURIComponent((product.brand ? product.brand + ' ' : '') + (product.model_number || product.name))}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-indigo-600 hover:underline"
                      >
                        Search →
                      </a>
                    )}
                  </div>
                </td>

                {/* Brand */}
                <td className="px-3 py-3 text-gray-600 font-medium">
                  {product.brand || '-'}
                </td>

                {/* Dynamic spec columns */}
                {specColumns.map((col) => (
                  <td key={col} className="px-3 py-3 text-gray-600 whitespace-nowrap">
                    {productSpecMaps[index][col] || (
                      <span className="text-gray-300">-</span>
                    )}
                  </td>
                ))}

                {/* Price */}
                <td className="px-3 py-3 whitespace-nowrap">
                  {product.price_range ? (
                    <span className="text-emerald-600 font-semibold">
                      {product.price_range}
                    </span>
                  ) : product.price ? (
                    <span className="text-emerald-600 font-semibold">
                      {product.currency === 'ILS' ? '₪' : product.currency}
                      {product.price.toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-gray-300">-</span>
                  )}
                </td>

                {/* Why recommended */}
                <td className="px-3 py-3 max-w-[200px]">
                  <p
                    className="text-xs text-gray-500 line-clamp-3 cursor-help"
                    title={product.why_recommended || undefined}
                  >
                    {product.why_recommended || '-'}
                  </p>
                </td>

                {/* Action */}
                <td className="px-3 py-3 text-center">
                  <button
                    onClick={() => onAddToList(product)}
                    disabled={isAddingId === product.id}
                    className="px-3 py-1.5 text-xs font-medium
                               bg-indigo-100 text-indigo-700
                               hover:bg-indigo-600 hover:text-white
                               disabled:opacity-50 disabled:cursor-wait
                               rounded-lg transition-colors"
                  >
                    {isAddingId === product.id ? 'Adding...' : 'Add to List'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
