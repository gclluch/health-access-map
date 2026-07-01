import { test, expect } from '@playwright/test';

// T8: the 14 sub-score lenses live in subscores.json, fetched lazily. The default composite view must
// NOT pull it (that's the cold-load win); selecting a sub-score lens must, and the map must still boot.

test('default composite load does not fetch subscores.json', async ({ page }) => {
  let subscoresRequested = false;
  page.on('request', (r) => {
    if (r.url().includes('/subscores.json')) subscoresRequested = true;
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Rankings' })).toBeVisible({ timeout: 20_000 });
  expect(subscoresRequested).toBe(false);
});

test('deep-linking a sub-score lens lazily fetches subscores.json', async ({ page }) => {
  const subscores = page.waitForResponse((r) => r.url().includes('/subscores.json') && r.ok());
  await page.goto('/?metric=insurance_pctile');
  await expect(page.getByRole('button', { name: 'Rankings' })).toBeVisible({ timeout: 20_000 });
  await subscores; // resolves only if the lazy fetch fired
});
