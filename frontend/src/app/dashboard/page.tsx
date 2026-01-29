/**
 * Main dashboard page.
 */

'use client';

import { useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { TraceList } from '@/components/traces/TraceList';
import { TraceDetail } from '@/components/traces/TraceDetail';
import { SearchBar } from '@/components/search/SearchBar';
import { DraftModal } from '@/components/drafts/DraftModal';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function Dashboard() {
  // Initialize WebSocket connection
  useWebSocket();

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />

      <main className="flex-1 flex flex-col p-4 gap-4">
        {/* Search bar */}
        <section className="bg-surface rounded-lg p-4">
          <SearchBar />
        </section>

        {/* Main content - split view */}
        <div className="flex-1 flex gap-4 min-h-0">
          {/* Trace list - left sidebar */}
          <aside className="w-80 bg-surface rounded-lg overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b border-surface-hover">
              <h2 className="font-medium">Recent Traces</h2>
            </div>
            <div className="flex-1 overflow-y-auto">
              <TraceList />
            </div>
          </aside>

          {/* Trace detail - main area */}
          <section className="flex-1 bg-surface rounded-lg overflow-hidden">
            <TraceDetail />
          </section>
        </div>
      </main>

      {/* Draft modal */}
      <DraftModal />
    </div>
  );
}
