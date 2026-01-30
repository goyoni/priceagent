/**
 * Hook for detecting user's country with localStorage caching.
 * Calls the geolocation API once and caches the result.
 */

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';

const COUNTRY_STORAGE_KEY = 'priceagent_user_country';
const CACHE_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

interface CachedCountry {
  country: string;
  timestamp: number;
}

interface UseCountryResult {
  country: string;
  isLoading: boolean;
  error: string | null;
  setCountry: (country: string) => void;
  refresh: () => void;
}

/**
 * Get country from localStorage cache if valid.
 */
function getCachedCountry(): string | null {
  if (typeof window === 'undefined') return null;

  try {
    const stored = localStorage.getItem(COUNTRY_STORAGE_KEY);
    if (!stored) return null;

    const cached: CachedCountry = JSON.parse(stored);
    const now = Date.now();

    // Check if cache is still valid
    if (now - cached.timestamp < CACHE_DURATION_MS) {
      return cached.country;
    }

    // Cache expired
    localStorage.removeItem(COUNTRY_STORAGE_KEY);
    return null;
  } catch {
    return null;
  }
}

/**
 * Save country to localStorage cache.
 */
function setCachedCountry(country: string): void {
  if (typeof window === 'undefined') return;

  try {
    const cached: CachedCountry = {
      country,
      timestamp: Date.now(),
    };
    localStorage.setItem(COUNTRY_STORAGE_KEY, JSON.stringify(cached));
  } catch (error) {
    console.error('[Country] Failed to cache:', error);
  }
}

/**
 * Hook to get and cache user's country.
 */
export function useCountry(defaultCountry: string = 'IL'): UseCountryResult {
  const [country, setCountryState] = useState<string>(defaultCountry);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const detectCountry = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    // First check cache
    const cached = getCachedCountry();
    if (cached) {
      setCountryState(cached);
      setIsLoading(false);
      return;
    }

    // Fetch from API
    try {
      const result = await api.getCountry();
      setCountryState(result.country);
      setCachedCountry(result.country);
    } catch (err) {
      console.error('[Country] Detection failed:', err);
      setError('Could not detect country');
      // Keep default country
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Detect on mount
  useEffect(() => {
    detectCountry();
  }, [detectCountry]);

  // Manual override
  const setCountry = useCallback((newCountry: string) => {
    setCountryState(newCountry);
    setCachedCountry(newCountry);
  }, []);

  return {
    country,
    isLoading,
    error,
    setCountry,
    refresh: detectCountry,
  };
}
