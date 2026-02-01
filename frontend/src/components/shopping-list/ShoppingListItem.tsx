/**
 * ShoppingListItem component for displaying a single item in the shopping list.
 */

'use client';

import type { ShoppingListItem as ShoppingListItemType } from '@/lib/types';
import { formatAddedTime } from '@/lib/shoppingList';

interface ShoppingListItemProps {
  item: ShoppingListItemType;
  onRemove: (id: string) => void;
  onEdit?: (id: string) => void;
}

export function ShoppingListItem({
  item,
  onRemove,
  onEdit,
}: ShoppingListItemProps) {
  return (
    <div className="flex items-start justify-between p-4 bg-white border border-gray-200 rounded-lg
                    hover:border-gray-300 transition-colors group shadow-soft">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="text-gray-800 font-medium truncate">{item.product_name}</h3>
          {item.source === 'discovery' && (
            <span className="px-2 py-0.5 text-xs bg-indigo-50 text-indigo-600 rounded-full">
              AI
            </span>
          )}
        </div>

        {item.model_number && (
          <p className="text-sm text-gray-500 mt-0.5">{item.model_number}</p>
        )}

        {item.specs_summary && (
          <p className="text-xs text-gray-400 mt-1 line-clamp-1">
            {item.specs_summary}
          </p>
        )}

        <p className="text-xs text-gray-400 mt-2">
          Added {formatAddedTime(item.added_at)}
        </p>
      </div>

      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {onEdit && (
          <button
            onClick={() => onEdit(item.id)}
            className="p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100
                     rounded-lg transition-colors"
            title="Edit"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
              />
            </svg>
          </button>
        )}
        <button
          onClick={() => onRemove(item.id)}
          className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50
                   rounded-lg transition-colors"
          title="Remove from list"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
