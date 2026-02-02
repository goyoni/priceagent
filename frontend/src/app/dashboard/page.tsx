/**
 * Main dashboard page with authentication protection.
 */

'use client';

import { Suspense, useState, useEffect, useCallback } from 'react';
import { Header } from '@/components/layout/Header';
import { TraceList } from '@/components/traces/TraceList';
import { TraceDetail } from '@/components/traces/TraceDetail';
import { SearchBar } from '@/components/search/SearchBar';
import { DraftModal } from '@/components/drafts/DraftModal';
import { LogViewer } from '@/components/logs/LogViewer';
import { useWebSocket } from '@/hooks/useWebSocket';

type DashboardTab = 'traces' | 'logs';
type AuthState = 'checking' | 'required' | 'authenticated' | 'open';

const AUTH_STORAGE_KEY = 'dashboard_auth_token';

export default function Dashboard() {
  const [authState, setAuthState] = useState<AuthState>('checking');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<DashboardTab>('traces');

  // Check auth status on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';

        // First check if auth is required
        const infoRes = await fetch(`${apiUrl}/traces/auth/info`);
        const info = await infoRes.json();

        if (!info.auth_required) {
          // Development mode - no auth needed
          setAuthState('open');
          return;
        }

        // Auth is required - check if we have a stored token
        const storedToken = localStorage.getItem(AUTH_STORAGE_KEY);
        if (storedToken) {
          // Verify the stored token
          const checkRes = await fetch(`${apiUrl}/traces/auth/check?auth=${encodeURIComponent(storedToken)}`);
          if (checkRes.ok) {
            setAuthState('authenticated');
            return;
          }
          // Token invalid, clear it
          localStorage.removeItem(AUTH_STORAGE_KEY);
        }

        setAuthState('required');
      } catch (err) {
        console.error('Auth check failed:', err);
        // On error, assume open access (development)
        setAuthState('open');
      }
    };

    checkAuth();
  }, []);

  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const res = await fetch(`${apiUrl}/traces/auth/check?auth=${encodeURIComponent(password)}`);

      if (res.ok) {
        // Store token and mark authenticated
        localStorage.setItem(AUTH_STORAGE_KEY, password);
        setAuthState('authenticated');
      } else {
        setAuthError('Invalid password');
      }
    } catch (err) {
      setAuthError('Authentication failed');
    }
  }, [password]);

  // Show loading while checking auth
  if (authState === 'checking') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">
        <div className="text-slate-400">Checking access...</div>
      </div>
    );
  }

  // Show login form if auth required
  if (authState === 'required') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">
        <div className="bg-slate-800 rounded-lg p-8 w-full max-w-md">
          <h1 className="text-xl font-semibold mb-6 text-center">Dashboard Access</h1>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label htmlFor="password" className="block text-sm text-slate-400 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg
                         text-white placeholder-slate-400 focus:outline-none focus:ring-2
                         focus:ring-cyan-500 focus:border-transparent"
                placeholder="Enter dashboard password"
                autoFocus
              />
            </div>
            {authError && (
              <div className="text-red-400 text-sm">{authError}</div>
            )}
            <button
              type="submit"
              className="w-full py-2 bg-cyan-600 hover:bg-cyan-500 text-white font-medium
                       rounded-lg transition-colors"
            >
              Access Dashboard
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Authenticated or open access - show dashboard
  return <DashboardContent activeTab={activeTab} setActiveTab={setActiveTab} />;
}

function DashboardContent({
  activeTab,
  setActiveTab,
}: {
  activeTab: DashboardTab;
  setActiveTab: (tab: DashboardTab) => void;
}) {
  // Initialize WebSocket connection
  useWebSocket();

  return (
    <div className="min-h-screen flex flex-col bg-slate-900 text-white">
      <Header />

      <main className="flex-1 flex flex-col p-4 gap-4">
        {/* Search bar */}
        <section className="bg-slate-800 rounded-lg p-4">
          <SearchBar />
        </section>

        {/* Tab navigation */}
        <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('traces')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'traces'
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Traces
            </span>
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'logs'
                ? 'bg-cyan-500/20 text-cyan-400'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Logs
            </span>
          </button>
        </div>

        {/* Main content */}
        {activeTab === 'traces' ? (
          <div className="flex-1 flex gap-4 min-h-0">
            {/* Trace list - left sidebar */}
            <aside className="w-80 bg-slate-800 rounded-lg overflow-hidden flex flex-col">
              <div className="px-4 py-3 border-b border-slate-700">
                <h2 className="font-medium text-white">Recent Traces</h2>
              </div>
              <div className="flex-1 overflow-y-auto">
                <Suspense fallback={<div className="p-4 text-center text-slate-400">Loading...</div>}>
                  <TraceList />
                </Suspense>
              </div>
            </aside>

            {/* Trace detail - main area */}
            <section className="flex-1 bg-slate-800 rounded-lg overflow-hidden">
              <TraceDetail />
            </section>
          </div>
        ) : (
          <div className="flex-1 min-h-0">
            <LogViewer />
          </div>
        )}
      </main>

      {/* Draft modal */}
      <DraftModal />
    </div>
  );
}
