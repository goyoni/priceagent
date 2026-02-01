/**
 * Client-side logging module.
 *
 * Provides structured logging for the frontend with:
 * - Different log levels (debug, info, warn, error)
 * - Console output in development
 * - Batched sending to backend in production
 * - Session and context tracking
 * - Error capturing with stack traces
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEntry {
  level: LogLevel;
  message: string;
  context?: Record<string, unknown>;
  timestamp: string;
  session_id?: string;
  url?: string;
  user_agent?: string;
}

// Configuration from environment
const config = {
  environment: process.env.NEXT_PUBLIC_ENVIRONMENT || 'development',
  logLevel: (process.env.NEXT_PUBLIC_LOG_LEVEL || 'debug') as LogLevel,
  sendToServer: process.env.NEXT_PUBLIC_LOG_SEND_TO_SERVER === 'true',
  apiUrl: process.env.NEXT_PUBLIC_API_URL || '',
  batchSize: 10,
  batchIntervalMs: 5000,
};

const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

// Session ID for correlating logs
let sessionId: string | null = null;

function getSessionId(): string {
  if (sessionId) return sessionId;

  if (typeof window !== 'undefined') {
    sessionId = sessionStorage.getItem('log_session_id');
    if (!sessionId) {
      sessionId = `log_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      sessionStorage.setItem('log_session_id', sessionId);
    }
  } else {
    sessionId = `log_${Date.now()}`;
  }

  return sessionId;
}

// Log buffer for batching
const logBuffer: LogEntry[] = [];
let flushTimeout: NodeJS.Timeout | null = null;

/**
 * Check if a log level should be output based on config.
 */
function shouldLog(level: LogLevel): boolean {
  return LOG_LEVEL_PRIORITY[level] >= LOG_LEVEL_PRIORITY[config.logLevel];
}

/**
 * Format log entry for console output.
 */
function formatForConsole(entry: LogEntry): string {
  const contextStr = entry.context
    ? ' ' + JSON.stringify(entry.context)
    : '';
  return `[${entry.level.toUpperCase()}] ${entry.message}${contextStr}`;
}

/**
 * Get console method for log level.
 */
function getConsoleMethod(level: LogLevel): 'log' | 'info' | 'warn' | 'error' {
  switch (level) {
    case 'debug':
      return 'log';
    case 'info':
      return 'info';
    case 'warn':
      return 'warn';
    case 'error':
      return 'error';
  }
}

/**
 * Create a log entry.
 */
function createLogEntry(
  level: LogLevel,
  message: string,
  context?: Record<string, unknown>
): LogEntry {
  return {
    level,
    message,
    context,
    timestamp: new Date().toISOString(),
    session_id: getSessionId(),
    url: typeof window !== 'undefined' ? window.location.href : undefined,
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
  };
}

/**
 * Schedule sending logs to server.
 */
function scheduleFlush(): void {
  if (!config.sendToServer || flushTimeout) return;

  flushTimeout = setTimeout(() => {
    flushLogs();
    flushTimeout = null;
  }, config.batchIntervalMs);
}

/**
 * Send buffered logs to server.
 */
async function flushLogs(): Promise<void> {
  if (logBuffer.length === 0) return;

  const logs = [...logBuffer];
  logBuffer.length = 0;

  try {
    await fetch(`${config.apiUrl}/api/analytics/logs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ logs }),
    });
  } catch (error) {
    // Re-queue logs on failure (up to a limit)
    if (logBuffer.length < 100) {
      logBuffer.push(...logs);
    }
    // Don't log the error to avoid infinite loop
    console.error('[Logger] Failed to send logs to server:', error);
  }
}

/**
 * Main log function.
 */
function log(level: LogLevel, message: string, context?: Record<string, unknown>): void {
  if (!shouldLog(level)) return;

  const entry = createLogEntry(level, message, context);

  // Always log to console in development
  if (config.environment === 'development' || level === 'error') {
    const method = getConsoleMethod(level);
    if (context) {
      console[method](formatForConsole(entry), context);
    } else {
      console[method](formatForConsole(entry));
    }
  }

  // Buffer for server in production
  if (config.sendToServer) {
    logBuffer.push(entry);

    // Flush immediately if buffer is full or on error
    if (logBuffer.length >= config.batchSize || level === 'error') {
      flushLogs();
    } else {
      scheduleFlush();
    }
  }
}

/**
 * Create a logger with a specific context/namespace.
 */
export function createLogger(namespace: string) {
  return {
    debug: (message: string, context?: Record<string, unknown>) =>
      log('debug', message, { ...context, namespace }),

    info: (message: string, context?: Record<string, unknown>) =>
      log('info', message, { ...context, namespace }),

    warn: (message: string, context?: Record<string, unknown>) =>
      log('warn', message, { ...context, namespace }),

    error: (message: string, context?: Record<string, unknown>) =>
      log('error', message, { ...context, namespace }),
  };
}

// Default logger instance
export const logger = {
  debug: (message: string, context?: Record<string, unknown>) =>
    log('debug', message, context),

  info: (message: string, context?: Record<string, unknown>) =>
    log('info', message, context),

  warn: (message: string, context?: Record<string, unknown>) =>
    log('warn', message, context),

  error: (message: string, context?: Record<string, unknown>) =>
    log('error', message, context),

  /**
   * Log an error with stack trace.
   */
  captureError: (error: Error, context?: Record<string, unknown>) => {
    log('error', error.message, {
      ...context,
      error_name: error.name,
      stack: error.stack?.split('\n').slice(0, 10).join('\n'),
    });
  },

  /**
   * Create a child logger with namespace.
   */
  child: createLogger,

  /**
   * Flush all buffered logs immediately.
   */
  flush: flushLogs,
};

// Auto-capture unhandled errors
if (typeof window !== 'undefined') {
  window.addEventListener('error', (event) => {
    logger.error('Uncaught error', {
      message: event.message,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      stack: event.error?.stack,
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    logger.error('Unhandled promise rejection', {
      reason: String(event.reason),
      stack: event.reason?.stack,
    });
  });

  // Flush logs before page unload
  window.addEventListener('beforeunload', () => {
    if (logBuffer.length > 0 && config.sendToServer) {
      // Use sendBeacon for reliable delivery
      navigator.sendBeacon(
        `${config.apiUrl}/api/analytics/logs`,
        JSON.stringify({ logs: logBuffer })
      );
    }
  });
}

export default logger;
