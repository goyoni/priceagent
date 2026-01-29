/**
 * Client-side analytics and event tracking.
 *
 * Tracks user interactions for:
 * - Engagement metrics (searches, clicks, contacts)
 * - Performance monitoring
 * - Error tracking
 */

// Event types
export type EventCategory =
  | 'page_view'
  | 'search'
  | 'result_interaction'
  | 'contact'
  | 'error'
  | 'performance';

export interface AnalyticsEvent {
  category: EventCategory;
  action: string;
  label?: string;
  value?: number;
  data?: Record<string, unknown>;
  timestamp: number;
}

// Session tracking
let sessionId: string | null = null;

function getSessionId(): string {
  if (sessionId) return sessionId;

  // Try to get from localStorage
  if (typeof window !== 'undefined') {
    sessionId = localStorage.getItem('analytics_session_id');
    if (!sessionId) {
      sessionId = `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('analytics_session_id', sessionId);
    }
  } else {
    sessionId = `sess_${Date.now()}`;
  }

  return sessionId;
}

// Event queue for batching
const eventQueue: AnalyticsEvent[] = [];
let flushTimeout: NodeJS.Timeout | null = null;

/**
 * Track an analytics event.
 */
export function track(
  category: EventCategory,
  action: string,
  options?: {
    label?: string;
    value?: number;
    data?: Record<string, unknown>;
  }
): void {
  const event: AnalyticsEvent = {
    category,
    action,
    label: options?.label,
    value: options?.value,
    data: options?.data,
    timestamp: Date.now(),
  };

  // Add to queue
  eventQueue.push(event);

  // Log to console in development
  if (process.env.NODE_ENV === 'development') {
    console.log('[Analytics]', category, action, options);
  }

  // Schedule flush
  scheduleFlush();
}

/**
 * Schedule sending events to server.
 */
function scheduleFlush(): void {
  if (flushTimeout) return;

  flushTimeout = setTimeout(() => {
    flushEvents();
    flushTimeout = null;
  }, 1000); // Batch events for 1 second
}

/**
 * Send queued events to server.
 */
async function flushEvents(): Promise<void> {
  if (eventQueue.length === 0) return;

  const events = [...eventQueue];
  eventQueue.length = 0;

  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
    await fetch(`${apiUrl}/api/analytics/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': getSessionId(),
      },
      body: JSON.stringify({ events }),
    });
  } catch (error) {
    // Re-queue events on failure
    eventQueue.push(...events);
    console.error('[Analytics] Failed to send events:', error);
  }
}

// Convenience functions

/**
 * Track a page view.
 */
export function trackPageView(page: string, referrer?: string): void {
  track('page_view', 'view', {
    label: page,
    data: { referrer, url: typeof window !== 'undefined' ? window.location.href : '' },
  });
}

/**
 * Track a search.
 */
export function trackSearch(
  query: string,
  resultsCount: number,
  durationMs: number
): void {
  track('search', 'submit', {
    label: query,
    value: resultsCount,
    data: { durationMs },
  });
}

/**
 * Track result interaction.
 */
export function trackResultClick(
  seller: string,
  position: number,
  price?: number
): void {
  track('result_interaction', 'click', {
    label: seller,
    value: position,
    data: { price },
  });
}

/**
 * Track seller contact.
 */
export function trackSellerContact(
  seller: string,
  method: 'whatsapp' | 'phone' | 'email',
  product?: string
): void {
  track('contact', method, {
    label: seller,
    data: { product },
  });
}

/**
 * Track draft generation.
 */
export function trackDraftGenerate(sellerCount: number): void {
  track('result_interaction', 'generate_draft', {
    value: sellerCount,
  });
}

/**
 * Track draft copy.
 */
export function trackDraftCopy(seller: string): void {
  track('result_interaction', 'copy_draft', {
    label: seller,
  });
}

/**
 * Track error.
 */
export function trackError(
  errorType: string,
  message: string,
  stack?: string
): void {
  track('error', errorType, {
    label: message,
    data: { stack: stack?.slice(0, 500) },
  });
}

/**
 * Track performance metric.
 */
export function trackPerformance(
  metric: string,
  value: number,
  unit: string = 'ms'
): void {
  track('performance', metric, {
    value,
    data: { unit },
  });
}

// Auto-track page views on route change (for Next.js)
if (typeof window !== 'undefined') {
  // Track initial page view
  trackPageView(window.location.pathname, document.referrer);

  // Track navigation
  const originalPushState = history.pushState;
  history.pushState = function (...args) {
    originalPushState.apply(history, args);
    trackPageView(window.location.pathname);
  };

  // Track popstate (back/forward)
  window.addEventListener('popstate', () => {
    trackPageView(window.location.pathname);
  });

  // Track errors
  window.addEventListener('error', (event) => {
    trackError('uncaught_error', event.message, event.error?.stack);
  });

  window.addEventListener('unhandledrejection', (event) => {
    trackError('unhandled_rejection', String(event.reason));
  });

  // Flush events before page unload
  window.addEventListener('beforeunload', () => {
    if (eventQueue.length > 0) {
      // Use sendBeacon for reliable delivery
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
      navigator.sendBeacon(
        `${apiUrl}/api/analytics/events`,
        JSON.stringify({ events: eventQueue, session_id: getSessionId() })
      );
    }
  });
}
