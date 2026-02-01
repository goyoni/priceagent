/**
 * Header component for the dashboard.
 */

import Link from 'next/link';
import { StatusIndicator } from './StatusIndicator';

export function Header() {
  return (
    <header className="h-14 bg-slate-800 border-b border-slate-700 px-4 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <h1 className="text-lg font-semibold text-white">
          Agent Dashboard
        </h1>
        <nav className="flex items-center gap-4">
          <Link
            href="/sellers"
            className="text-sm text-slate-400 hover:text-white transition-colors"
          >
            Sellers DB
          </Link>
        </nav>
      </div>
      <StatusIndicator />
    </header>
  );
}
