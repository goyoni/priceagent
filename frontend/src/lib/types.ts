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
  session_id?: string;
  parent_trace_id?: string;  // Links to parent trace in conversation flow
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
  child_traces?: Trace[];  // Nested child traces (refinements)
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

// Product Discovery types
export interface DiscoveredProduct {
  id: string;
  name: string;
  brand?: string;
  model_number?: string;
  category: string;
  key_specs: string[];
  price_range?: string;
  why_recommended: string;
  // Additional fields from search results
  price?: number;
  currency?: string;
  url?: string;
  rating?: number;
  match_score?: 'high' | 'medium' | 'low' | 'unknown';
  criteria_match?: {
    matched?: string[];
    adapted?: string[];
    unknown?: string[];
    unmet?: string[];
  };
  market_reality_note?: string;
}

export interface DiscoveryCriterion {
  attribute: string;
  value?: string;
  ideal_value?: string;
  market_value?: string;
  market_context?: string;
  is_flexible?: boolean;
  source?: string;
  confidence?: 'high' | 'medium' | 'low';
  explanation?: string;
}

export interface DiscoverySearchAttempt {
  query: string;
  strategy: 'specific_model' | 'local_language' | 'category';
  results: number;
  scrapers?: Array<{ name: string; count: number }>;
}

export interface DiscoverySearchSummary {
  original_requirement: string;
  category: string;
  country: string;
  criteria_used: DiscoveryCriterion[];
  recommended_models_searched?: string[];
  search_attempts: DiscoverySearchAttempt[];
  total_products_found: number;
  research_quality?: 'good' | 'moderate' | 'limited' | 'unknown';
  market_notes?: string;
  filtering_notes?: string;
  error?: string;
}

export interface DiscoveryResponse {
  products: DiscoveredProduct[];
  search_summary?: DiscoverySearchSummary;
  no_results_message?: string;
  suggestions?: string[];
  criteria_feedback?: string[];
  market_notes?: string;
  filtering_notes?: string;
}

// Conversation types for product discovery
export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  traceId?: string;  // Associated trace ID for this message
  productsSnapshot?: DiscoveredProduct[];  // Products at this point in conversation
}

// Shopping List types
export interface ShoppingListItem {
  id: string;
  product_name: string;
  model_number?: string;
  specs_summary?: string;
  source: 'manual' | 'discovery';
  added_at: string;
}

export interface PriceSearchSession {
  id: string;
  trace_id?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  country: string;
  started_at: string;
  completed_at?: string;
  error?: string;
}
