/**
 * Utility functions for the dashboard.
 */

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with clsx.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a date string for display.
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '';
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format a duration in milliseconds.
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format a price with currency.
 */
export function formatPrice(price: number, currency: string = 'ILS'): string {
  return `${price.toLocaleString()} ${currency}`;
}

/**
 * Escape HTML for safe display.
 */
export function escapeHtml(text: string | null | undefined): string {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Truncate text to a maximum length.
 */
export function truncate(text: string | null | undefined, maxLength: number): string {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + '...';
}

/**
 * Extract domain from URL.
 */
export function extractDomain(url: string): string {
  try {
    const parsed = new URL(url);
    let domain = parsed.hostname;
    if (domain.startsWith('www.')) {
      domain = domain.slice(4);
    }
    return domain;
  } catch {
    return url;
  }
}

/**
 * Generate WhatsApp link.
 */
export function generateWhatsAppLink(
  phone: string,
  message?: string
): string {
  const cleanPhone = phone.replace(/[^0-9]/g, '');
  let link = `https://wa.me/${cleanPhone}`;
  if (message) {
    link += `?text=${encodeURIComponent(message)}`;
  }
  return link;
}
