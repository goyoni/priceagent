/**
 * SearchBar component for running queries.
 */

'use client';

import { useState } from 'react';
import { useSearchStore } from '@/stores/useSearchStore';
import { Button } from '@/components/ui/Button';

export function SearchBar() {
  const { query, setQuery, isSearching, runSearch } = useSearchStore();
  const [inputValue, setInputValue] = useState(query);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) {
      setQuery(inputValue);
      runSearch(inputValue);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        placeholder="Search for products (e.g., iPhone 15, Samsung TV...)"
        className="flex-1 px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg
                   text-white placeholder-slate-400
                   focus:outline-none focus:border-cyan-500"
        disabled={isSearching}
      />
      <Button type="submit" disabled={isSearching || !inputValue.trim()}>
        {isSearching ? 'Searching...' : 'Search'}
      </Button>
    </form>
  );
}
