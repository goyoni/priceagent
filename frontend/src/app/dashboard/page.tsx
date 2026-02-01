/**
 * Main dashboard page.
 */

'use client';

import { Suspense, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { TraceList } from '@/components/traces/TraceList';
import { TraceDetail } from '@/components/traces/TraceDetail';
import { SearchBar } from '@/components/search/SearchBar';
import { DraftModal } from '@/components/drafts/DraftModal';
import { LogViewer } from '@/components/logs/LogViewer';
import { useWebSocket } from '@/hooks/useWebSocket';

type DashboardTab = 'traces' | 'logs';

export default function Dashboard() {
  // Initialize WebSocket connection
  useWebSocket();

  const [activeTab, setActiveTab] = useState<DashboardTab>('traces');

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
