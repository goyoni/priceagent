/**
 * Hook to check if dashboard access is available.
 * In development: always shows dashboard link
 * In production: hides dashboard link from users
 */

import { useState, useEffect } from 'react';

interface DashboardAccess {
  showDashboardLink: boolean;
  isLoading: boolean;
}

export function useDashboardAccess(): DashboardAccess {
  const [showDashboardLink, setShowDashboardLink] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkAccess = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
        const res = await fetch(`${apiUrl}/traces/auth/info`);
        const info = await res.json();

        // Show link only if auth is NOT required (development mode)
        // In production (auth required), don't show link to regular users
        setShowDashboardLink(!info.auth_required);
      } catch (err) {
        // On error, assume development (show link)
        setShowDashboardLink(true);
      } finally {
        setIsLoading(false);
      }
    };

    checkAccess();
  }, []);

  return { showDashboardLink, isLoading };
}
