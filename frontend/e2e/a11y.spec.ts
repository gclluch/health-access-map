import AxeBuilder from '@axe-core/playwright';
import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

// axe over the states a user actually reaches: the default map, a selected ZIP, the modal, and
// the phone layout. Scoped to WCAG A/AA so a failure means a real conformance defect rather than
// a best-practice suggestion. Like the smoke suite, these select through the rankings list rather
// than naming a ZIP, so they hold against the 5-ZCTA CI fixture and a real national build alike.
//
// The map canvas is excluded. deck.gl paints into a WebGL surface with no DOM to inspect, so axe
// can only report noise there; the keyboard route to the same data (SearchBox, RankingsList) is
// covered by the assertions below instead.

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const DETAIL_PANEL = /^ZIP \d{5} detail$/;

const scan = (page: Page) =>
  new AxeBuilder({ page }).withTags(TAGS).exclude('.maplibregl-canvas-container').analyze();

async function ready(page: Page) {
  await expect(page.getByRole('button', { name: 'Rankings' })).toBeVisible({ timeout: 20_000 });
}

async function selectFirstZip(page: Page) {
  await ready(page);
  // Desktop opens the rail by default; narrower/compact contexts may still start collapsed.
  if ((await page.getByTestId('ranking-row').count()) === 0) {
    await page.getByRole('button', { name: 'Rankings' }).click();
  }
  await page.getByTestId('ranking-row').first().click();
}

test('the default map view has no WCAG A/AA violations', async ({ page }) => {
  await page.goto('/');
  await ready(page);

  expect((await scan(page)).violations).toEqual([]);
});

test('the detail panel has no violations and takes focus when a ZIP is selected', async ({ page }) => {
  await page.goto('/');
  await selectFirstZip(page);

  const panel = page.getByRole('region', { name: DETAIL_PANEL });
  await expect(panel).toBeVisible();
  // Selection is the app's core interaction; without a focus move it is silent to a screen reader.
  await expect(panel).toBeFocused();

  expect((await scan(page)).violations).toEqual([]);
});

test('the methodology dialog has no violations and traps focus', async ({ page }) => {
  await page.goto('/');
  await ready(page);
  await page.getByRole('button', { name: 'How to read this' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  expect((await scan(page)).violations).toEqual([]);

  // Tab must not escape into the inert background behind the dialog.
  for (let i = 0; i < 12; i++) await page.keyboard.press('Tab');
  await expect(dialog.locator(':focus')).toHaveCount(1);

  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
});

test.describe('phone width', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('has no violations, and the sheet never buries a control it leaves in the DOM', async ({ page }) => {
    await page.goto('/');
    await ready(page);
    expect((await scan(page)).violations).toEqual([]);

    // The map's own zoom controls must survive the full-bleed legend (WCAG 2.5.1 wants a
    // single-pointer alternative to pinch).
    await expect(page.locator('.maplibregl-ctrl-zoom-in')).toBeVisible();
    const covering = await page.evaluate(() => {
      const el = document.querySelector('.maplibregl-ctrl-zoom-in');
      if (!el) return 'missing';
      const r = el.getBoundingClientRect();
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return top && (el === top || el.contains(top)) ? null : (top?.tagName ?? 'unknown');
    });
    expect(covering).toBeNull();

    // Selecting a ZIP takes the same bottom anchor, so the rankings toggle is dropped rather
    // than stacked underneath where it is tappable by nobody but still reachable by Tab.
    await selectFirstZip(page);
    await expect(page.getByRole('region', { name: DETAIL_PANEL })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Rankings' })).toBeHidden();
  });
});
