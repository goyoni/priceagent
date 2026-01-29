/**
 * ResultsParser utility for parsing trace tool_output into structured data.
 */

import type { SearchResult, BundleResult } from './types';

/**
 * Parse bundle opportunities from tool output.
 */
export function parseBundleResults(text: string): BundleResult[] {
  const bundleMatch = text.match(/=== BUNDLE OPPORTUNITIES \((\d+) stores\) ===/);
  if (!bundleMatch) return [];

  // Get bundle section
  const bundleSectionMatch = text.match(/=== BUNDLE OPPORTUNITIES.*?(?=\n\n=== [^B]|$)/s);
  if (!bundleSectionMatch) return [];

  const bundles: BundleResult[] = [];

  // Parse each store entry
  const storePattern = /(\d+)\.\s+([^\n]+?)(?:\s+\(Rating:\s*([\d.]+)\/5\))?\n([\s\S]*?)(?=\n\d+\.|$)/g;
  let match;

  while ((match = storePattern.exec(bundleSectionMatch[0])) !== null) {
    const index = parseInt(match[1]);
    const storeName = match[2].trim();
    const rating = match[3] ? parseFloat(match[3]) : undefined;
    const details = match[4];

    // Extract product count
    const offersMatch = details.match(/Offers\s+(\d+)\/(\d+)\s+products/);
    const productCount = offersMatch ? parseInt(offersMatch[1]) : 0;
    const totalProducts = offersMatch ? parseInt(offersMatch[2]) : 0;

    // Extract products
    const products: BundleResult['products'] = [];
    const productPattern = /^\s+-\s+([^:]+):\s+([\d,]+)\s+(\w+)(?:\s*\|\s*(https?:\/\/[^\s]+))?/gm;
    let productMatch;

    while ((productMatch = productPattern.exec(details)) !== null) {
      products.push({
        name: productMatch[1].trim(),
        price: parseInt(productMatch[2].replace(/,/g, '')),
        currency: productMatch[3],
        url: productMatch[4] || undefined,
      });
    }

    // Extract total
    const totalMatch = details.match(/Total:\s+([\d,]+)/);
    const totalPrice = totalMatch ? parseInt(totalMatch[1].replace(/,/g, '')) : undefined;

    // Extract contact
    const contactMatch = details.match(/Contact:\s*(\+?[\d\s-]+)/);
    const contact = contactMatch ? contactMatch[1].replace(/[\s-]/g, '') : undefined;

    bundles.push({
      index,
      storeName,
      rating,
      productCount,
      totalProducts,
      products,
      totalPrice,
      contact,
    });
  }

  return bundles;
}

/**
 * Parse per-product sections from tool output.
 */
export function parseProductSections(text: string): Array<{
  productName: string;
  results: SearchResult[];
}> {
  const sections: Array<{ productName: string; results: SearchResult[] }> = [];

  // Match product section headers
  const sectionPattern = /\n=== ([^=\n]+) ===\n/g;
  const matches: Array<{ name: string; startIndex: number }> = [];
  let match;

  while ((match = sectionPattern.exec(text)) !== null) {
    if (match[1].includes('BUNDLE OPPORTUNITIES')) continue;
    matches.push({ name: match[1].trim(), startIndex: match.index + match[0].length });
  }

  // Extract results for each section
  for (let i = 0; i < matches.length; i++) {
    const startIdx = matches[i].startIndex;
    const endIdx = i + 1 < matches.length
      ? matches[i + 1].startIndex - matches[i + 1].name.length - 8
      : text.length;

    const sectionText = text.slice(startIdx, endIdx);
    const results = parseSearchResults(sectionText);

    sections.push({
      productName: matches[i].name,
      results,
    });
  }

  return sections;
}

/**
 * Parse search results from a section of text.
 */
export function parseSearchResults(text: string): SearchResult[] {
  const results: SearchResult[] = [];

  // Match each result entry
  const resultPattern = /(\d+)\.\s+([^\n]+?)(?:\s+\(Rating:\s*([\d.]+)\/5\))?(?:\s+\[([^\]]+)\])?\n([\s\S]*?)(?=\n\d+\.|$)/g;
  let match;

  while ((match = resultPattern.exec(text)) !== null) {
    const index = parseInt(match[1]);
    const seller = match[2].trim();
    const rating = match[3] ? parseFloat(match[3]) : undefined;
    const details = match[5];

    // Extract price
    const priceMatch = details.match(/Price:\s*([\d,]+)\s*(\w+)?/);
    const price = priceMatch ? parseInt(priceMatch[1].replace(/,/g, '')) : undefined;
    const currency = priceMatch?.[2] || 'ILS';

    // Extract URL
    const urlMatch = details.match(/URL:\s*(https?:\/\/[^\s]+)/);
    const url = urlMatch ? urlMatch[1] : undefined;

    // Extract contact
    const contactMatch = details.match(/Contact:\s*(\+?[\d\s-]+)/);
    const phone = contactMatch ? contactMatch[1].replace(/[\s-]/g, '') : undefined;

    results.push({
      index,
      seller,
      rating,
      price,
      currency,
      url,
      phone,
    });
  }

  return results;
}
