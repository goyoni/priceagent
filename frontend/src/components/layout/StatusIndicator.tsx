/**
 * StatusIndicator component for showing connection status.
 */

'use client';

import { useTraceStore } from '@/stores/useTraceStore';
import { cn } from '@/lib/utils';

export function StatusIndicator() {
  const connectionStatus = useTraceStore((state) => state.connectionStatus);

  const statusConfig = {
    connecting: {
      color: 'bg-warning',
      text: 'Connecting...',
    },
    connected: {
      color: 'bg-success',
      text: 'Connected',
    },
    disconnected: {
      color: 'bg-error',
      text: 'Disconnected',
    },
  };

  const config = statusConfig[connectionStatus];

  return (
    <div className="flex items-center gap-2 text-sm text-secondary">
      <span
        className={cn('w-2 h-2 rounded-full animate-pulse', config.color)}
      />
      <span>{config.text}</span>
    </div>
  );
}
