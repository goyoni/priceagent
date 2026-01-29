/**
 * SellerRow component for displaying a single seller in a table.
 */

'use client';

import { useSearchStore } from '@/stores/useSearchStore';
import { formatPrice, generateWhatsAppLink } from '@/lib/utils';
import type { SearchResult } from '@/lib/types';

interface SellerRowProps {
  result: SearchResult;
  productName: string;
}

export function SellerRow({ result, productName }: SellerRowProps) {
  const { toggleSellerSelection, isSellerSelected } = useSearchStore();

  const handleToggle = () => {
    if (!result.phone) return;

    toggleSellerSelection({
      seller_name: result.seller,
      phone_number: result.phone,
      product_name: productName,
      listed_price: result.price || 0,
    });
  };

  return (
    <tr className="border-b border-surface-hover hover:bg-surface-hover/50">
      <td className="px-3 py-2 text-secondary">{result.index}</td>
      <td className="px-3 py-2 font-medium">{result.seller}</td>
      <td className="px-3 py-2">
        {result.rating ? (
          <span className="inline-flex items-center px-2 py-0.5 rounded bg-warning/20 text-warning text-xs">
            ★ {result.rating}
          </span>
        ) : (
          <span className="text-secondary">-</span>
        )}
      </td>
      <td className="px-3 py-2">
        {result.price ? (
          <span className="text-success font-medium">
            {formatPrice(result.price, result.currency)}
          </span>
        ) : (
          <span className="text-secondary">-</span>
        )}
      </td>
      <td className="px-3 py-2">
        {result.url ? (
          <a
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline text-sm"
          >
            View →
          </a>
        ) : (
          <span className="text-secondary">-</span>
        )}
      </td>
      <td className="px-3 py-2">
        {result.phone ? (
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isSellerSelected(result.seller, result.phone)}
              onChange={handleToggle}
              className="w-4 h-4 cursor-pointer"
            />
            <a
              href={generateWhatsAppLink(result.phone)}
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
  );
}
