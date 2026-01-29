/**
 * ResultsTable component for displaying search results for a product.
 */

'use client';

import { SellerRow } from './SellerRow';
import type { SearchResult } from '@/lib/types';

interface ResultsTableProps {
  productName: string;
  results: SearchResult[];
}

export function ResultsTable({ productName, results }: ResultsTableProps) {
  if (!results || results.length === 0) return null;

  return (
    <div className="mb-6">
      <h4 className="text-sm font-medium text-primary mb-2">{productName}</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-hover text-left text-secondary">
              <th className="px-3 py-2 w-10">#</th>
              <th className="px-3 py-2">Seller</th>
              <th className="px-3 py-2 w-20">Rating</th>
              <th className="px-3 py-2 w-28">Price</th>
              <th className="px-3 py-2 w-20">Link</th>
              <th className="px-3 py-2 w-24">Contact</th>
            </tr>
          </thead>
          <tbody>
            {results.map((result) => (
              <SellerRow
                key={`${productName}-${result.index}`}
                result={result}
                productName={productName}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
