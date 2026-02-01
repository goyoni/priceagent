/**
 * API client for communicating with the FastAPI backend.
 */

import type {
  Trace,
  TraceListResponse,
  GenerateDraftsRequest,
  GenerateDraftsResponse,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get list of recent traces.
   */
  async getTraces(limit: number = 50): Promise<Trace[]> {
    const data = await this.fetch<TraceListResponse>(
      `/traces/?limit=${limit}`
    );
    return data.traces;
  }

  /**
   * Get a single trace by ID.
   */
  async getTrace(traceId: string): Promise<Trace> {
    return this.fetch<Trace>(`/traces/${traceId}`);
  }

  /**
   * Delete a trace by ID.
   */
  async deleteTrace(traceId: string): Promise<void> {
    await this.fetch(`/traces/${traceId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Run an agent query.
   */
  async runQuery(
    query: string,
    agent: string = 'research'
  ): Promise<{ trace_id: string; status: string }> {
    return this.fetch('/agent/run', {
      method: 'POST',
      body: JSON.stringify({ query, agent }),
    });
  }

  /**
   * Generate negotiation draft messages.
   */
  async generateDrafts(
    request: GenerateDraftsRequest
  ): Promise<GenerateDraftsResponse> {
    return this.fetch('/agent/generate-drafts', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Look up seller contacts by domain.
   */
  async lookupContacts(
    domains: string[]
  ): Promise<Record<string, { domain: string; seller_name?: string; phone_number?: string; whatsapp_number?: string }>> {
    const data = await this.fetch<{
      contacts: Record<string, { domain: string; seller_name?: string; phone_number?: string; whatsapp_number?: string }>;
    }>('/api/sellers/contacts', {
      method: 'POST',
      body: JSON.stringify({ domains }),
    });
    return data.contacts;
  }

  /**
   * Get all sellers.
   */
  async getSellers(): Promise<Array<{
    id: number;
    seller_name: string;
    domain: string;
    phone_number?: string;
    whatsapp_number?: string;
    website_url?: string;
    rating?: number;
  }>> {
    const data = await this.fetch<{ sellers: Array<{
      id: number;
      seller_name: string;
      domain: string;
      phone_number?: string;
      whatsapp_number?: string;
      website_url?: string;
      rating?: number;
    }> }>('/api/sellers/');
    return data.sellers;
  }

  /**
   * Run a product discovery query.
   */
  async runDiscovery(
    query: string,
    country: string = 'IL'
  ): Promise<{ trace_id: string; status: string }> {
    return this.fetch('/agent/run', {
      method: 'POST',
      body: JSON.stringify({ query, agent: 'discovery', country }),
    });
  }

  /**
   * Run a discovery refinement with conversation history.
   */
  async runDiscoveryRefinement(
    query: string,
    country: string = 'IL',
    conversationHistory: Array<{ role: string; content: string }>,
    sessionId: string
  ): Promise<{ trace_id: string; status: string }> {
    return this.fetch('/agent/run', {
      method: 'POST',
      body: JSON.stringify({
        query,
        agent: 'discovery',
        country,
        conversation_history: conversationHistory,
        session_id: sessionId,
      }),
    });
  }

  /**
   * Get country from IP detection.
   */
  async getCountry(): Promise<{ country: string; source: string }> {
    return this.fetch('/api/geo/country');
  }

  /**
   * Start a price search for shopping list items.
   */
  async startPriceSearch(
    items: Array<{ product_name: string; model_number?: string }>,
    country: string = 'IL'
  ): Promise<{ session_id: string; trace_id: string; status: string }> {
    return this.fetch('/api/shopping-list/search-prices', {
      method: 'POST',
      body: JSON.stringify({ items, country }),
    });
  }

  /**
   * Get the status of a price search session.
   */
  async getSearchStatus(sessionId: string): Promise<{
    session_id: string;
    status: string;
    started_at: string;
    completed_at?: string;
    trace_id?: string;
    error?: string;
  }> {
    return this.fetch(`/api/shopping-list/search-status/${sessionId}`);
  }
}

// Export singleton instance
export const api = new ApiClient();
