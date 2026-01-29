/**
 * Header component for the dashboard.
 */

import Link from 'next/link';
import { StatusIndicator } from './StatusIndicator';

export function Header() {
  return (
    <header className="h-14 bg-surface border-b border-surface-hover px-4 flex items-center justify-between">
      <div className="flex items-center gap-6">
        <h1 className="text-lg font-semibold">
          Agent Dashboard
        </h1>
        <nav className="flex items-center gap-4">
          <Link
            href="/sellers"
            className="text-sm text-muted hover:text-foreground transition-colors"
          >
            Sellers DB
          </Link>
        </nav>
      </div>
      <StatusIndicator />
    </header>
  );
}
