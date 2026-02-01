/**
 * DiscoveryResultsTable component for displaying discovered products.
 * Shows products with specs, price range, and "Add to List" buttons.
 */

'use client';

import type { DiscoveredProduct } from '@/lib/types';

interface DiscoveryResultsTableProps {
  products: DiscoveredProduct[];
  onAddToList: (product: DiscoveredProduct) => void;
  isAddingId?: string;
}

export function DiscoveryResultsTable({
  products,
  onAddToList,
  isAddingId,
}: DiscoveryResultsTableProps) {
  if (!products || products.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-800">
        Recommended Products ({products.length})
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="px-3 py-3">#</th>
              <th className="px-3 py-3">Product</th>
              <th className="px-3 py-3">Brand</th>
              <th className="px-3 py-3">Key Specs</th>
              <th className="px-3 py-3">Price Range</th>
              <th className="px-3 py-3">Why Recommended</th>
              <th className="px-3 py-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product, index) => (
              <DiscoveryProductRow
                key={product.id}
                product={product}
                index={index + 1}
                onAddToList={onAddToList}
                isAdding={isAddingId === product.id}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface DiscoveryProductRowProps {
  product: DiscoveredProduct;
  index: number;
  onAddToList: (product: DiscoveredProduct) => void;
  isAdding: boolean;
}

function DiscoveryProductRow({
  product,
  index,
  onAddToList,
  isAdding,
}: DiscoveryProductRowProps) {
  return (
    <tr className="border-b border-gray-200/50 hover:bg-gray-50">
      <td className="px-3 py-3 text-gray-400">{index}</td>
      <td className="px-3 py-3">
        <div className="font-medium text-gray-800">{product.name}</div>
        {product.model_number && (
          <div className="text-sm font-mono text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded inline-block mt-1">
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
              View product
            </a>
          ) : (
            <a
              href={`https://www.google.com/search?q=${encodeURIComponent((product.brand ? product.brand + ' ' : '') + (product.model_number || product.name))}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-indigo-600 hover:underline"
            >
              Search on Google
            </a>
          )}
        </div>
      </td>
      <td className="px-3 py-3 text-gray-600">{product.brand || '-'}</td>
      <td className="px-3 py-3">
        {product.key_specs.length > 0 ? (
          <ul className="space-y-0.5">
            {product.key_specs.slice(0, 3).map((spec, i) => (
              <li key={i} className="text-xs text-gray-500">
                • {spec}
              </li>
            ))}
            {product.key_specs.length > 3 && (
              <li className="text-xs text-gray-400">
                +{product.key_specs.length - 3} more
              </li>
            )}
          </ul>
        ) : (
          <span className="text-gray-400">-</span>
        )}
      </td>
      <td className="px-3 py-3">
        {product.price_range ? (
          <span className="text-emerald-600 font-medium">
            {product.price_range}
          </span>
        ) : product.price ? (
          <span className="text-emerald-600 font-medium">
            {product.currency === 'ILS' ? '₪' : product.currency}
            {product.price.toLocaleString()}
          </span>
        ) : (
          <span className="text-gray-400">-</span>
        )}
      </td>
      <td className="px-3 py-3 max-w-xs">
        <p
          className="text-xs text-gray-500 line-clamp-2 cursor-help"
          title={product.why_recommended || undefined}
        >
          {product.why_recommended || '-'}
        </p>
      </td>
      <td className="px-3 py-3 text-center">
        <button
          onClick={() => onAddToList(product)}
          disabled={isAdding}
          className="px-3 py-1.5 text-xs font-medium
                     bg-indigo-50 text-indigo-600
                     hover:bg-indigo-500 hover:text-gray-800
                     disabled:opacity-50 disabled:cursor-wait
                     rounded-lg transition-colors"
        >
          {isAdding ? 'Adding...' : 'Add to List'}
        </button>
      </td>
    </tr>
  );
}
