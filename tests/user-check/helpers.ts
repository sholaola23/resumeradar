import { test as base, expect, type Page, type Response } from '@playwright/test';
import { join } from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const fixtures = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures.json', import.meta.url)), 'utf8'),
);

const LOCAL_HOSTS = new Set(['127.0.0.1', 'localhost']);
// Web fonts are the only outside files the pages ask for. They are answered
// here with an empty file, so the browser never reaches Google.
const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);

type Guard = { blocked: string[]; consoleErrors: string[]; allowConsole: RegExp[] };

export const test = base.extend<{ guard: Guard }>({
  guard: [
    async ({ page, context }, use) => {
      const guard: Guard = { blocked: [], consoleErrors: [], allowConsole: [] };
      // Each test is a new visitor, so one test's rate limits never fail another.
      expect((await page.request.post('/__user-check/reset')).status()).toBe(200);
      await context.grantPermissions(['clipboard-read', 'clipboard-write']);
      await context.route('**/*', (route) => {
        const url = new URL(route.request().url());
        if (url.protocol === 'data:' || url.protocol === 'blob:' || LOCAL_HOSTS.has(url.hostname)) {
          return route.continue();
        }
        if (FONT_HOSTS.has(url.hostname)) {
          return route.fulfill({ status: 200, contentType: 'text/css', body: '' });
        }
        guard.blocked.push(url.href);
        return route.abort('blockedbyclient');
      });
      page.on('console', (msg) => {
        if (msg.type() === 'error') guard.consoleErrors.push(msg.text());
      });
      page.on('pageerror', (err) => guard.consoleErrors.push(`page error: ${err.message}`));

      await use(guard);

      const unexpected = guard.consoleErrors.filter((text) => !guard.allowConsole.some((re) => re.test(text)));
      expect(guard.blocked, 'the page tried to reach an outside address').toEqual([]);
      expect(unexpected, 'console errors').toEqual([]);
      const serverBlocked = await (await page.request.get('/__user-check/blocked')).json();
      expect(serverBlocked, 'the server tried to reach an outside address').toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** axe (WCAG 2.1 A and AA) on the page as it is now, plus no sideways scroll. */
export async function checkPage(page: Page, label: string) {
  // Let fade-ins finish first, or axe measures half-faded text as low contrast.
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'));
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`,
  );
  expect(summary, `axe violations on ${label}`).toEqual([]);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, `sideways scroll on ${label} (px)`).toBeLessThanOrEqual(0);
  // USER_CHECK_SCREENSHOTS=<folder> keeps a screenshot of every checked page.
  const dir = process.env.USER_CHECK_SCREENSHOTS;
  if (dir) {
    mkdirSync(dir, { recursive: true });
    const name = `${label.replace(/[^a-z0-9]+/gi, '-')}-${test.info().project.name}.png`;
    await page.screenshot({ path: join(dir, name), fullPage: false });
  }
}

/** Fill the job description and paste the sample CV, then scan. */
export async function scanPasted(page: Page) {
  await page.goto('/');
  await page.locator('.tab-btn[data-tab="paste"]').click();
  await page.locator('#resumeText').fill(fixtures.cv_text);
  await page.locator('#jobDescription').fill(fixtures.job_description);
  await page.locator('#scanBtn').click();
  await expectScanResults(page);
}

/**
 * Wait for the scan to end in results or an error, and fail at once on an
 * error with its text. Waiting for a response by URL would hang until the
 * test timeout when the scan calls the wrong address.
 */
export async function expectScanResults(page: Page) {
  const results = page.locator('#results');
  const error = page.locator('#errorMessage');
  await expect(results.or(error).first(), 'scan finished').toBeVisible({ timeout: 30_000 });
  if (await error.isVisible()) {
    throw new Error(`scan showed an error instead of results: ${(await error.innerText()).trim()}`);
  }
  await expect(results).toBeVisible();
  await expect(page.locator('#scoreNumber')).toHaveText(/\d/);
}

export function isApi(path: string) {
  return (r: Response) => new URL(r.url()).pathname === path;
}
