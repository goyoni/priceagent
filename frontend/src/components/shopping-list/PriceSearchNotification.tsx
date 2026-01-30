/**
 * PriceSearchNotification component for showing search status toast.
 */

'use client';

import { useEffect, useState } from 'react';
import { useShoppingListStore } from '@/stores/useShoppingListStore';

interface PriceSearchNotificationProps {
  onViewResults: (traceId: string) => void;
}

export function PriceSearchNotification({
  onViewResults,
}: PriceSearchNotificationProps) {
  const { activeSearchSession, isSearching } = useShoppingListStore();
  const [isVisible, setIsVisible] = useState(false);
  const [hasNewResults, setHasNewResults] = useState(false);

  // Show notification when search completes
  useEffect(() => {
    if (activeSearchSession?.status === 'completed' && !isSearching) {
      setIsVisible(true);
      setHasNewResults(true);

      // Auto-hide after 10 seconds
      const timeout = setTimeout(() => {
        setIsVisible(false);
      }, 10000);

      return () => clearTimeout(timeout);
    }
  }, [activeSearchSession?.status, isSearching]);

  // Show searching status
  if (isSearching && activeSearchSession) {
    return (
      <div className="fixed bottom-20 right-4 z-50 animate-slide-in">
        <div className="bg-slate-800 border border-slate-600 rounded-xl shadow-xl p-4 max-w-sm">
          <div className="flex items-center gap-3">
            <div className="flex-shrink-0">
              <svg className="w-5 h-5 text-cyan-400 animate-spin" viewBox="0 0 24 24">
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
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium">Searching prices...</p>
              <p className="text-slate-400 text-xs truncate">
                You can continue browsing while we search
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Show completion notification
  if (!isVisible || !activeSearchSession) return null;

  const isSuccess = activeSearchSession.status === 'completed';
  const isFailed = activeSearchSession.status === 'failed';

  return (
    <div className="fixed bottom-20 right-4 z-50 animate-slide-in">
      <div
        className={`bg-slate-800 border rounded-xl shadow-xl p-4 max-w-sm ${
          isSuccess ? 'border-emerald-500/50' : isFailed ? 'border-red-500/50' : 'border-slate-600'
        }`}
      >
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-0.5">
            {isSuccess ? (
              <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className={`text-sm font-medium ${isSuccess ? 'text-emerald-400' : 'text-red-400'}`}>
              {isSuccess ? 'Price search complete!' : 'Price search failed'}
            </p>
            {isSuccess ? (
              <p className="text-slate-400 text-xs mt-0.5">
                Click to view results in the dashboard
              </p>
            ) : (
              <p className="text-slate-500 text-xs mt-0.5 line-clamp-2">
                {activeSearchSession.error || 'An error occurred'}
              </p>
            )}
          </div>
          <button
            onClick={() => setIsVisible(false)}
            className="flex-shrink-0 text-slate-500 hover:text-white transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {isSuccess && activeSearchSession.trace_id && (
          <button
            onClick={() => {
              onViewResults(activeSearchSession.trace_id!);
              setIsVisible(false);
              setHasNewResults(false);
            }}
            className="mt-3 w-full py-2 bg-emerald-500/20 text-emerald-400 text-sm rounded-lg
                     hover:bg-emerald-500 hover:text-white transition-colors"
          >
            View Results
          </button>
        )}
      </div>
    </div>
  );
}
