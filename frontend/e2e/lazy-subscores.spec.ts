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

test('opening a detail panel fetches subscores.json and fills the sub-score rows', async ({ page }) => {
  const subscores = page.waitForResponse((r) => r.url().includes('/subscores.json') && r.ok());
  await page.goto('/');
  const rankings = page.getByRole('button', { name: 'Rankings' });
  await expect(rankings).toBeVisible({ timeout: 20_000 });
  if ((await page.getByTestId('ranking-row').count()) === 0) {
    await rankings.click();
  }
  await page.getByTestId('ranking-row').first().click();
  await expect(page.getByRole('group', { name: /What drives the score/ })).toBeVisible();
  await subscores; // the panel open itself must trigger the lazy fetch (not just a lens select)
  // force: same flyTo-repaint oscillation as compare.spec; the row is the top hit-target.
  // [aria-expanded] picks the EXPLORE THE LAYERS accordion row over the driver-bar buttons.
  await page.locator('button[aria-expanded]').filter({ hasText: 'Health need' }).first()
    .click({ force: true });
  // the merged columns must surface as real percentiles, not a wall of "no data"
  const rows = page.getByRole('button', { name: /Chronic disease|Behavioral risk|Mental & social|Disability/ });
  await expect(rows.first()).toBeVisible();
  await expect(rows.getByText(/\d+(?:st|nd|rd|th) pctile/).first()).toBeVisible();
});

test('deep-linking a sub-score lens lazily fetches subscores.json', async ({ page }) => {
  const subscores = page.waitForResponse((r) => r.url().includes('/subscores.json') && r.ok());
  await page.goto('/?metric=insurance_pctile');
  await expect(page.getByRole('button', { name: 'Rankings' })).toBeVisible({ timeout: 20_000 });
  await subscores; // resolves only if the lazy fetch fired
});
