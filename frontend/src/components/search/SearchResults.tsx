/**
 * SearchResults component for displaying parsed search results.
 */

'use client';

import { useMemo, useEffect, useState } from 'react';
import { useTraceStore } from '@/stores/useTraceStore';
import { useSearchStore } from '@/stores/useSearchStore';
import { useDraftStore } from '@/stores/useDraftStore';
import { BundleSection } from './BundleSection';
import { ResultsTable } from './ResultsTable';
import { Button } from '@/components/ui/Button';
import { parseBundleResults, parseProductSections } from '@/lib/parser';
import { api } from '@/lib/api';
import type { BundleResult, SearchResult } from '@/lib/types';

// Extract domain from URL
function extractDomain(url: string): string | null {
  try {
    const parsed = new URL(url);
    let domain = parsed.hostname.toLowerCase();
    if (domain.startsWith('www.')) {
      domain = domain.slice(4);
    }
    // Skip google.com URLs
    if (domain.includes('google.com')) {
      return null;
    }
    return domain;
  } catch {
    return null;
  }
}

// Normalize store name for matching
function normalizeStoreName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[|]/g, ' ')  // Replace pipe with space
    .replace(/[^\w\s]/g, '')  // Remove special chars
    .replace(/\s+/g, ' ')  // Normalize whitespace
    .trim();
}

// Normalize without spaces for looser matching
function normalizeNoSpaces(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^\w]/g, '');  // Remove all non-word chars including spaces
}

export function SearchResults() {
  const { selectedTrace } = useTraceStore();
  const { selectedSellers, clearSelection } = useSearchStore();
  const { generateDrafts, isGenerating } = useDraftStore();

  // State for enriched results with contacts from DB
  const [contactsLookup, setContactsLookup] = useState<Record<string, string>>({});
  const [sellersByName, setSellersByName] = useState<Record<string, string>>({});
  const [sellersByNameNoSpaces, setSellersByNameNoSpaces] = useState<Record<string, string>>({});

  // Parse results from trace tool_output
  const { bundles, productSections } = useMemo(() => {
    if (!selectedTrace?.spans) {
      return { bundles: [], productSections: [] };
    }

    // Find span with tool_output
    const toolSpan = selectedTrace.spans.find((s) => s.tool_output);
    if (!toolSpan?.tool_output) {
      return { bundles: [], productSections: [] };
    }

    const text = toolSpan.tool_output;
    return {
      bundles: parseBundleResults(text),
      productSections: parseProductSections(text),
    };
  }, [selectedTrace]);

  // Load all sellers for name-based matching
  useEffect(() => {
    api.getSellers()
      .then((sellers) => {
        const byName: Record<string, string> = {};
        const byNameNoSpaces: Record<string, string> = {};
        const byDomain: Record<string, string> = {};

        sellers.forEach((s) => {
          const phone = s.whatsapp_number || s.phone_number;
          if (phone) {
            // Add by normalized name
            const normalizedName = normalizeStoreName(s.seller_name);
            byName[normalizedName] = phone;

            // Add by no-spaces name for looser matching
            const noSpacesName = normalizeNoSpaces(s.seller_name);
            byNameNoSpaces[noSpacesName] = phone;

            // Also add by domain
            if (s.domain) {
              byDomain[s.domain] = phone;
            }
          }
        });

        setSellersByName(byName);
        setSellersByNameNoSpaces(byNameNoSpaces);
        setContactsLookup(byDomain);
      })
      .catch((err) => {
        console.error('Failed to load sellers:', err);
      });
  }, []);

  // Helper to find contact for a bundle or result
  const findContact = (storeName: string, url?: string): string | undefined => {
    // First try by domain
    if (url) {
      const domain = extractDomain(url);
      if (domain && contactsLookup[domain]) {
        return contactsLookup[domain];
      }
    }

    // Then try by name (with spaces)
    const normalizedName = normalizeStoreName(storeName);

    // Check for exact match
    if (sellersByName[normalizedName]) {
      return sellersByName[normalizedName];
    }

    // Check for partial matches (e.g., "electricshop" in "אלקטריק שופ electricshop")
    for (const [name, phone] of Object.entries(sellersByName)) {
      if (normalizedName.includes(name) || name.includes(normalizedName)) {
        return phone;
      }
    }

    // Try no-spaces matching for looser match (handles "electricshop" vs "electric shop")
    const noSpacesName = normalizeNoSpaces(storeName);
    if (sellersByNameNoSpaces[noSpacesName]) {
      return sellersByNameNoSpaces[noSpacesName];
    }

    // Check for partial no-spaces matches
    for (const [name, phone] of Object.entries(sellersByNameNoSpaces)) {
      if (noSpacesName.includes(name) || name.includes(noSpacesName)) {
        return phone;
      }
    }

    return undefined;
  };

  // Enrich bundles with contacts from DB
  const enrichedBundles: BundleResult[] = useMemo(() => {
    if (!bundles) return [];
    return bundles.map((bundle) => {
      // If bundle already has contact, keep it
      if (bundle.contact) return bundle;

      // Try to find contact by store name first
      const contact = findContact(bundle.storeName, bundle.products?.[0]?.url);
      if (contact) {
        return { ...bundle, contact };
      }

      return bundle;
    });
  }, [bundles, contactsLookup, sellersByName, sellersByNameNoSpaces]);

  // Enrich product sections with contacts from DB
  const enrichedProductSections = useMemo(() => {
    if (!productSections) return [];
    return productSections.map((section) => ({
      ...section,
      results: (section.results || []).map((r): SearchResult => {
        // If result already has phone, keep it
        if (r.phone) return r;

        // Try to find contact
        const phone = findContact(r.seller, r.url);
        if (phone) {
          return { ...r, phone };
        }

        return r;
      }),
    }));
  }, [productSections, contactsLookup, sellersByName, sellersByNameNoSpaces]);

  const hasResults = (bundles?.length || 0) > 0 || (productSections?.length || 0) > 0;

  if (!hasResults) {
    return null;
  }

  const handleGenerateDrafts = () => {
    if (selectedSellers && selectedSellers.length > 0) {
      generateDrafts(selectedSellers);
    }
  };

  return (
    <div className="mt-4">
      {/* Bulk actions bar */}
      {selectedSellers && selectedSellers.length > 0 && (
        <div className="flex items-center gap-4 mb-4 p-3 bg-primary/10 rounded-lg">
          <span className="text-sm">
            <strong>{selectedSellers.length}</strong> sellers selected
          </span>
          <Button
            size="sm"
            onClick={handleGenerateDrafts}
            disabled={isGenerating}
          >
            {isGenerating ? 'Generating...' : '📝 Generate Drafts'}
          </Button>
          <Button size="sm" variant="ghost" onClick={clearSelection}>
            Clear
          </Button>
        </div>
      )}

      {/* Bundle opportunities */}
      {enrichedBundles && enrichedBundles.length > 0 && <BundleSection bundles={enrichedBundles} />}

      {/* Per-product results */}
      {enrichedProductSections.map((section) => (
        <ResultsTable
          key={section.productName}
          productName={section.productName}
          results={section.results}
        />
      ))}
    </div>
  );
}
