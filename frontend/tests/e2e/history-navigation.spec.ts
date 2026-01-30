import { test, expect } from '@playwright/test';

/**
 * E2E tests for history navigation and URL-based tab switching.
 */

test.describe('Tab Navigation', () => {
  test('should update URL when switching tabs', async ({ page }) => {
    await page.goto('/');

    // Default tab should be 'discover' (Find Products)
    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Click on Price Search tab
    await page.getByRole('button', { name: 'Price Search' }).click();
    await expect(page).toHaveURL(/tab=search/);

    // Click on Shopping List tab
    await page.getByRole('button', { name: 'Shopping List' }).click();
    await expect(page).toHaveURL(/tab=shopping-list/);

    // Click back on Find Products tab
    await page.getByRole('button', { name: 'Find Products' }).click();
    await expect(page).toHaveURL(/tab=discover/);
  });

  test('should navigate to correct tab from URL', async ({ page }) => {
    // Navigate directly to search tab
    await page.goto('/?tab=search');
    // The Price Search button should have the active styling (cyan border)
    const searchButton = page.getByRole('button', { name: 'Price Search' });
    await expect(searchButton).toBeVisible();
    await expect(searchButton).toHaveCSS('border-color', 'rgba(6, 182, 212, 0.3)');

    // Navigate directly to discover tab
    await page.goto('/?tab=discover');
    const discoverButton = page.getByRole('button', { name: 'Find Products' });
    await expect(discoverButton).toBeVisible();
    await expect(discoverButton).toHaveCSS('border-color', 'rgba(6, 182, 212, 0.3)');
  });
});

test.describe('History Navigation', () => {
  test.beforeEach(async ({ page }) => {
    // Set up mock history in localStorage before navigating
    await page.addInitScript(() => {
      // Add mock search history
      const searchHistory = [
        {
          id: 'search_mock_1',
          query: 'Test Product Search',
          timestamp: Date.now() - 3600000,
          resultCount: 5,
          traceId: 'mock-trace-id-123',
        },
      ];
      localStorage.setItem('shoppingagent_search_history', JSON.stringify(searchHistory));

      // Add mock discovery history
      const discoveryHistory = [
        {
          id: 'discovery_mock_1',
          query: 'Test Discovery Query',
          timestamp: Date.now() - 7200000,
          productCount: 10,
          traceId: 'mock-discovery-trace-456',
        },
      ];
      localStorage.setItem('shoppingagent_discovery_history', JSON.stringify(discoveryHistory));
    });
  });

  test('should show discovery history on Find Products tab', async ({ page }) => {
    await page.goto('/?tab=discover');

    // Wait for page to load and history to render
    await page.waitForLoadState('networkidle');

    // History section should show discovery history
    await expect(page.getByText('Test Discovery Query')).toBeVisible();
  });

  test('should show search history on Price Search tab', async ({ page }) => {
    await page.goto('/?tab=search');

    // Wait for page to load and history to render
    await page.waitForLoadState('networkidle');

    // History section should show search history
    await expect(page.getByText('Test Product Search')).toBeVisible();
  });

  test('should update URL when clicking search history item with traceId', async ({ page }) => {
    await page.goto('/?tab=search');
    await page.waitForLoadState('networkidle');

    // Click on history item
    await page.getByText('Test Product Search').click();

    // URL should include trace parameter
    await expect(page).toHaveURL(/trace=mock-trace-id-123/);
    await expect(page).toHaveURL(/tab=search/);
  });

  test('should update URL when clicking discovery history item with traceId', async ({ page }) => {
    await page.goto('/?tab=discover');
    await page.waitForLoadState('networkidle');

    // Click on history item
    await page.getByText('Test Discovery Query').click();

    // URL should include trace parameter
    await expect(page).toHaveURL(/trace=mock-discovery-trace-456/);
    await expect(page).toHaveURL(/tab=discover/);
  });

  test('should navigate to correct tab and trace from URL', async ({ page }) => {
    // Navigate directly to a search trace
    await page.goto('/?tab=search&trace=mock-trace-id-123');

    // Should be on search tab - verify by button being visible
    await expect(page.getByRole('button', { name: 'Price Search' })).toBeVisible();

    // URL should have both params
    await expect(page).toHaveURL(/tab=search/);
    await expect(page).toHaveURL(/trace=mock-trace-id-123/);
  });

  test('should delete history item when clicking delete button', async ({ page }) => {
    await page.goto('/?tab=search');
    await page.waitForLoadState('networkidle');

    // Verify history item exists
    await expect(page.getByText('Test Product Search')).toBeVisible();

    // Hover to show delete button, then click
    const historyItem = page.getByText('Test Product Search');
    await historyItem.hover();
    await page.getByTestId('delete-history-item').click();

    // Item should be removed
    await expect(page.getByText('Test Product Search')).not.toBeVisible();
  });
});

test.describe('Dashboard Trace Navigation', () => {
  test('should update URL when clicking trace in dashboard', async ({ page }) => {
    await page.goto('/dashboard');

    // Wait for traces to load (or show empty state)
    await page.waitForLoadState('networkidle');

    // If there are traces, clicking one should update URL
    const traceItem = page.getByTestId('trace-item').first();

    // Check if any trace exists
    const traceCount = await page.getByTestId('trace-item').count();
    if (traceCount > 0) {
      await traceItem.click();
      await expect(page).toHaveURL(/trace=/);
    }
  });
});
