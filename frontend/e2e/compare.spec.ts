import { test, expect } from '@playwright/test';

// Exercises the wired-up compare flow: rankings row -> detail panel -> pin to comparison tray.
test('pin a ZIP from the rankings list into the comparison tray', async ({ page }) => {
  await page.goto('/');
  const rankings = page.getByRole('button', { name: 'Rankings' });
  await expect(rankings).toBeVisible({ timeout: 20_000 });
  // Desktop opens the rail by default; narrower/compact contexts may still start collapsed.
  if ((await page.getByTestId('ranking-row').count()) === 0) {
    await rankings.click();
  }

  await page.getByTestId('ranking-row').first().click();
  // the detail panel's "what drives the score" driver-share bar renders with per-dimension segments
  await expect(page.getByRole('group', { name: /What drives the score/ })).toBeVisible();
  const compareBtn = page.getByRole('button', { name: /Compare/ });
  await expect(compareBtn).toBeVisible();
  // force: the row click kicks off a map flyTo whose continuous repaint makes Playwright's
  // scroll-into-view stability check oscillate; the button is provably the top hit-target
  // (verified via elementFromPoint), so a forced click is correct, not a masked overlay.
  await compareBtn.click({ force: true });
  const tray = page.getByRole('region', { name: 'ZIP comparison' });
  await expect(tray).toBeVisible();
  await expect(tray.getByText('National disadvantage rank')).toBeVisible();
});
