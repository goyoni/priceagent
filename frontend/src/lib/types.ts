/**
 * TypeScript type definitions for the dashboard.
 */

export interface SellerInfo {
  name: string;
  website?: string;
  whatsapp_number?: string;
  reliability_score?: number;
  country: string;
  source: string;
}

export interface PriceOption {
  product_id: string;
  seller: SellerInfo;
  listed_price: number;
  currency: string;
  url: string;
  scraped_at: string;
}

export interface Span {
  id?: string;
  span_id?: string;
  parent_span_id?: string;
  name?: string;
  // API returns span_type, but we also support type for flexibility
  type?: 'function' | 'agent' | 'handoff' | 'tool' | 'llm_call' | 'tool_call' | 'agent_run';
  span_type?: 'function' | 'agent' | 'handoff' | 'tool' | 'llm_call' | 'tool_call' | 'agent_run';
  status?: 'running' | 'completed' | 'error';
  started_at?: string;
  ended_at?: string;
  duration_ms?: number;
  input?: string;
  output?: string;
  error?: string;
  model?: string;
  // LLM call specific
  system_prompt?: string;
  input_messages?: unknown;
  output_content?: string;
  input_tokens?: number;
  output_tokens?: number;
  cached?: boolean;
  // Tool call specific
  tool_name?: string;
  tool_input?: unknown;
  tool_output?: string;
  // Handoff specific
  from_agent?: string;
  to_agent?: string;
}

export interface OperationalSummary {
  // Search stats
  google_searches: number;
  google_searches_cached: number;
  zap_searches: number;
  zap_searches_cached: number;

  // Scrape stats
  page_scrapes: number;
  page_scrapes_cached: number;

  // Error/warning tracking
  errors: string[];
  warnings: string[];

  // Price extraction stats
  prices_extracted: number;
  prices_failed: number;

  // Contact extraction stats
  contacts_extracted: number;
  contacts_failed: number;
}

export interface Trace {
  id: string;
  input_prompt: string;
  final_output?: string;
  status: 'running' | 'completed' | 'error';
  started_at: string;
  ended_at?: string;
  total_tokens: number;
  total_duration_ms: number;
  error?: string;
  spans: Span[];
  operational_summary?: OperationalSummary;
}

export interface TraceListResponse {
  traces: Trace[];
}

export interface SearchResult {
  index: number;
  seller: string;
  rating?: number;
  price?: number;
  currency: string;
  url?: string;
  phone?: string;
}

export interface BundleResult {
  index: number;
  storeName: string;
  rating?: number;
  productCount: number;
  totalProducts: number;
  products: Array<{
    name: string;
    price: number;
    currency: string;
    url?: string;
  }>;
  totalPrice?: number;
  contact?: string;
}

export interface DraftMessage {
  seller_name: string;
  phone_number: string;
  product_name: string;
  message: string;
  wa_link: string;
}

export interface GenerateDraftsRequest {
  sellers: Array<{
    seller_name: string;
    phone_number: string;
    product_name: string;
    listed_price: number;
    currency?: string;
  }>;
  language?: string;
}

export interface GenerateDraftsResponse {
  drafts: DraftMessage[];
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';
