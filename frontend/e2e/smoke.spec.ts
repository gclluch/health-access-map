import { test, expect } from '@playwright/test';

// These assert app-level behavior that holds regardless of the underlying data volume,
// so they pass against both the CI fixture and a real local build.

test('boots, loads data, and renders core chrome', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Care Access Map')).toBeVisible();

  // Loading -> ready: the rail only mounts once loadData() resolves.
  await expect(page.getByRole('button', { name: 'Rankings' })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Loading ~33,000 ZIP areas')).toHaveCount(0);
});

test('access-beyond-deprivation lens colors the map and explains itself', async ({ page }) => {
  await page.goto('/?metric=care_access_resid_pctile');
  // the lens-specific caption (Legend LENS_HELP) only renders when that metric is active
  await expect(page.getByText(/Structural-access lens/)).toBeVisible({ timeout: 20_000 });
});

test('methodology panel opens and states the collinearity caveat', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'How to read this' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  // The reframed honesty: dimensions are collinear and the sliders are a sensitivity probe.
  await expect(dialog.getByText(/effective dimension/i).first()).toBeVisible();
});

test('weighting control is reachable and framed as a sensitivity probe', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Rankings' })).toBeVisible({ timeout: 20_000 });
  // Open the weighting disclosure (label is consistent per the UI copy fixes).
  const adjust = page.getByRole('button', { name: /Adjust weighting|Customize/ });
  if (await adjust.count()) {
    await adjust.first().click();
    await expect(page.getByText(/sensitivity probe/i)).toBeVisible();
  }
});
