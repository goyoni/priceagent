/**
 * BundleSection component for displaying bundle opportunities.
 */

'use client';

import { useState } from 'react';
import { useSearchStore } from '@/stores/useSearchStore';
import { formatPrice, generateWhatsAppLink } from '@/lib/utils';
import type { BundleResult } from '@/lib/types';

type SortOption = 'products' | 'price';

interface BundleSectionProps {
  bundles: BundleResult[];
}

export function BundleSection({ bundles }: BundleSectionProps) {
  const { toggleSellerSelection, isSellerSelected } = useSearchStore();
  const [sortBy, setSortBy] = useState<SortOption>('products');

  // Filter bundles to only show stores with at least 1 product found
  const validBundles = bundles?.filter(b => b.productCount >= 1) || [];

  // Don't render if no valid bundles
  if (validBundles.length === 0) return null;

  // Sort bundles based on selected option
  const sortedBundles = [...validBundles].sort((a, b) => {
    if (sortBy === 'price') {
      // Sort by total price (ascending) - lowest first
      const priceA = a.totalPrice ?? Infinity;
      const priceB = b.totalPrice ?? Infinity;
      return priceA - priceB;
    } else {
      // Sort by product count (descending), then by price (ascending)
      if (b.productCount !== a.productCount) {
        return b.productCount - a.productCount;
      }
      const priceA = a.totalPrice ?? Infinity;
      const priceB = b.totalPrice ?? Infinity;
      return priceA - priceB;
    }
  });

  // Limit to top 10 results
  const displayBundles = sortedBundles.slice(0, 10);

  const handleToggle = (bundle: BundleResult) => {
    if (!bundle.contact) return;

    // Use first product name or "Bundle" as product name
    const productName = bundle.products && bundle.products.length > 0
      ? bundle.products.map(p => p.name).join(', ')
      : 'Bundle';

    toggleSellerSelection({
      seller_name: bundle.storeName,
      phone_number: bundle.contact,
      product_name: productName,
      listed_price: bundle.totalPrice || 0,
    });
  };

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-secondary">
          Bundle Opportunities ({displayBundles.length} stores)
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-secondary">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortOption)}
            className="text-xs bg-surface border border-surface-hover rounded px-2 py-1 text-primary"
          >
            <option value="products">Most Products</option>
            <option value="price">Lowest Price</option>
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-hover text-left text-secondary">
              <th className="px-3 py-2 w-10">#</th>
              <th className="px-3 py-2">Store</th>
              <th className="px-3 py-2 w-20">Rating</th>
              <th className="px-3 py-2">Products</th>
              <th
                className="px-3 py-2 w-28 cursor-pointer hover:text-primary"
                onClick={() => setSortBy('price')}
              >
                Total Price {sortBy === 'price' && '↑'}
              </th>
              <th className="px-3 py-2 w-28">Contact</th>
            </tr>
          </thead>
          <tbody>
            {displayBundles.map((bundle, idx) => (
              <tr
                key={bundle.storeName}
                className="border-b border-surface-hover hover:bg-surface-hover/50"
              >
                <td className="px-3 py-2 text-secondary">{idx + 1}</td>
                <td className="px-3 py-2 font-medium">{bundle.storeName}</td>
                <td className="px-3 py-2">
                  {bundle.rating ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded bg-warning/20 text-warning text-xs">
                      ★ {bundle.rating}
                    </span>
                  ) : (
                    <span className="text-secondary">-</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <div className="text-xs">
                    <span className="text-primary">
                      {bundle.productCount}/{bundle.totalProducts}
                    </span>
                    {bundle.products && bundle.products.length > 0 && (
                      <ul className="mt-1 space-y-1">
                        {bundle.products.map((p, i) => (
                          <li key={i} className="flex items-center gap-2">
                            <span className="text-secondary">
                              {p.name}: {formatPrice(p.price, p.currency)}
                            </span>
                            {p.url && (
                              <a
                                href={p.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-primary hover:underline"
                              >
                                →
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2">
                  {bundle.totalPrice ? (
                    <span className="text-success font-medium">
                      {formatPrice(bundle.totalPrice, 'ILS')}
                    </span>
                  ) : (
                    <span className="text-secondary">-</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  {bundle.contact ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isSellerSelected(bundle.storeName, bundle.contact)}
                        onChange={() => handleToggle(bundle)}
                        className="w-4 h-4 cursor-pointer"
                      />
                      <a
                        href={generateWhatsAppLink(bundle.contact)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center px-2 py-1 rounded bg-[#25D366] text-white text-xs hover:bg-[#128C7E]"
                      >
                        💬
                      </a>
                    </div>
                  ) : (
                    <span className="text-secondary">-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
