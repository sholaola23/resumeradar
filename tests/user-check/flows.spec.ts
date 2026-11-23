// Each test.describe block matches a row in docs/feature-map.md.
import { test, expect, fixtures, checkPage, scanPasted, isApi } from './helpers';

test.describe('Scan with a CV and a job description', () => {
  test('home page loads and passes axe', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('#scanBtn')).toBeVisible();
    await checkPage(page, 'home');
  });

  test('scan with an uploaded DOCX shows the results page', async ({ page }) => {
    const docx = await (await page.request.get('/__user-check/sample-cv.docx')).body();
    await page.goto('/');
    await page.locator('#resumeFile').setInputFiles({
      name: 'sample_cv.docx',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      buffer: docx,
    });
    await expect(page.locator('#fileName')).toHaveText('sample_cv.docx');
    await page.locator('#jobDescription').fill(fixtures.job_description);
    const scan = page.waitForResponse(isApi('/api/scan'));
    await page.locator('#scanBtn').click();
    expect((await scan).status()).toBe(200);
    await expect(page.locator('#results')).toBeVisible();
    await expect(page.locator('#scoreNumber')).toHaveText(/\d/);
    await expect(page.locator('#missingKeywords')).not.toBeEmpty();
  });

  test('scan with pasted text shows the results page with suggestions', async ({ page }) => {
    await scanPasted(page);
    await expect(page.locator('#scoreHeading')).toContainText(/keyword coverage|match/i);
    await expect(page.locator('#aiSuggestions')).toContainText('Clear SQL and Python work'); // from the fake Claude reply
    await expect(page.locator('#matchedKeywords')).not.toBeEmpty();
    await checkPage(page, 'results');
  });

  test('example report runs a scan', async ({ page }) => {
    await page.goto('/');
    const scan = page.waitForResponse(isApi('/api/scan'));
    await page.locator('#demoScanBtn').click();
    expect((await scan).status()).toBe(200);
    await expect(page.locator('#results')).toBeVisible();
    await expect(page.locator('#scoreNumber')).toHaveText(/\d/);
  });

  test('scan with nothing filled in shows an error', async ({ page, guard }) => {
    // The browser's own form check, or the app's error box: either way no scan.
    guard.allowConsole.push(/status of 400/);
    await page.goto('/');
    await page.locator('#jobDescription').evaluate((el) => el.removeAttribute('required'));
    await page.locator('#scanBtn').click();
    await expect(page.locator('#errorMessage')).toBeVisible();
    await expect(page.locator('#results')).toBeHidden();
    await checkPage(page, 'scan error');
  });
});

test.describe('Cover letter', () => {
  test('writes a cover letter from the scan', async ({ page }) => {
    await scanPasted(page);
    const button = page.locator('#generateCoverLetterBtn');
    await button.scrollIntoViewIfNeeded();
    const call = page.waitForResponse(isApi('/api/generate/cover-letter'));
    await button.click();
    expect((await call).status()).toBe(200);
    await expect(page.locator('#coverLetterBody')).toContainText('Sample reply from the user check');
    await checkPage(page, 'cover letter');
  });
});

test.describe('Bullet and summary tools (API only)', () => {
  // No page on the site calls these since the builder was switched off, so
  // the check calls the routes the way that page did.
  test('improve a bullet', async ({ page }) => {
    const res = await page.request.post('/api/tools/enhance-bullet', {
      data: { bullet_text: 'Built weekly sales dashboards for store managers', job_context: fixtures.job_description },
    });
    expect(res.status()).toBe(200);
    expect(JSON.stringify(await res.json())).toContain('Sample reply from the user check');
  });

  test('write a summary', async ({ page }) => {
    const res = await page.request.post('/api/tools/generate-summary', {
      data: { resume_text: fixtures.cv_text, job_description: fixtures.job_description },
    });
    expect(res.status()).toBe(200);
    expect(JSON.stringify(await res.json())).toContain('Sample reply from the user check');
  });
});

test.describe('Report: download and email', () => {
  test('download the PDF report', async ({ page }) => {
    await scanPasted(page);
    const download = page.waitForEvent('download');
    await page.locator('#downloadReportBtn').click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.pdf$/);
    const path = await file.path();
    const { readFileSync } = await import('node:fs');
    expect(readFileSync(path).subarray(0, 4).toString()).toBe('%PDF');
  });

  test('email the report: confirm email, press confirm, report arrives', async ({ page, context }) => {
    const address = `jordan.${test.info().project.name}@example.com`;
    await scanPasted(page);
    await page.locator('#emailReportBtn').click();
    await expect(page.locator('#emailModal')).toBeVisible();
    await checkPage(page, 'email dialog');
    await page.locator('#emailInput').fill(address);
    await page.locator('#sendEmailBtn').click();
    await expect(page.locator('#emailWaitText')).toContainText(address);

    const outbox = async () => (await (await page.request.get('/__user-check/outbox')).json()) as any[];
    const confirm = (await outbox()).find((m) => m.to.includes(address) && /Confirm/.test(m.subject));
    expect(confirm, 'confirm email in the fake outbox').toBeTruthy();
    const token = /confirm-email\?t=([^\s"&]+)/.exec(confirm.text)?.[1];
    expect(token, 'confirm link in the email').toBeTruthy();

    // Open the link the way the inbox would (on this local server, not the live site).
    const inbox = await context.newPage();
    await inbox.goto(`/confirm-email?t=${token}`);
    await checkPage(inbox, 'confirm page');
    await inbox.getByRole('button').first().click();
    await expect(inbox.locator('body')).toContainText(/confirmed/i);
    await inbox.close();

    await page.bringToFront();
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.locator('#toastMessage')).toContainText(`Report sent to ${address}`, { timeout: 20_000 });
    const report = (await outbox()).find((m) => m.to.includes(address) && /Your ResumeRadar Report/.test(m.subject));
    expect(report, 'report email in the fake outbox').toBeTruthy();
    expect(report.attachments).toEqual(['ResumeRadar_Report.pdf']);
  });
});

test.describe('Share link', () => {
  test('share this job description opens with it filled in', async ({ page }) => {
    await scanPasted(page);
    const button = page.locator('[data-share-job]');
    await button.scrollIntoViewIfNeeded();
    await button.click();
    await expect(page.locator('#shareCard [data-share-status]')).not.toBeEmpty();
    const link = await page.evaluate(() => navigator.clipboard.readText());
    expect(link).toContain('#');
    expect(link).not.toContain('Jordan'); // the CV never goes in the link
    const local = new URL(link);
    await page.goto(`/${local.search}${local.hash}`);
    await expect(page.locator('#jobDescription')).toHaveValue(fixtures.job_description);
    await expect(page.locator('#resumeText')).toHaveValue('');
  });

  test('share page loads and passes axe', async ({ page }) => {
    await page.goto('/share');
    await expect(page.locator('h1')).toBeVisible();
    await checkPage(page, 'share page');
  });
});

test.describe('Newsletter sign-up', () => {
  test('sign up from the results page', async ({ page }) => {
    const address = `tips.${test.info().project.name}@example.com`;
    await scanPasted(page);
    const card = page.locator('#inlineGateCard');
    await expect(card).toBeVisible();
    await page.locator('#inlineGateFirstName').fill('Jordan');
    await page.locator('#inlineGateEmail').fill(address);
    const call = page.waitForResponse(isApi('/api/subscribe'));
    await card.locator('.inline-gate-btn').click();
    expect((await call).status()).toBe(200);
    await expect(page.locator('#toastMessage')).toContainText('Subscribed');
    await expect
      .poll(async () => (await (await page.request.get('/__user-check/beehiiv')).json()).map((c: any) => c.email))
      .toContain(address);
  });
});

test.describe('Was this useful?', () => {
  test('vote yes and send a comment', async ({ page }) => {
    await scanPasted(page);
    await page.locator('#feedbackYes').scrollIntoViewIfNeeded();
    await page.locator('#feedbackYes').click();
    await expect(page.locator('#feedbackForm')).toBeVisible();
    await page.locator('#feedbackComment').fill('Clear and quick, thanks.');
    const call = page.waitForResponse(isApi('/api/feedback'));
    await page.locator('#feedbackSend').click();
    expect((await call).status()).toBe(200);
    await expect(page.locator('#feedbackStatus')).toContainText(/thank/i);
  });
});

test.describe('Other pages', () => {
  for (const [label, path] of [
    ['privacy page', '/privacy'],
    ['role guides', '/ats-resume-checker/'],
  ] as const) {
    test(`${label} loads and passes axe`, async ({ page }) => {
      const res = await page.goto(path);
      expect(res?.status()).toBe(200);
      await expect(page.locator('h1')).toBeVisible();
      await checkPage(page, label);
    });
  }

  test('a role page loads and passes axe', async ({ page }) => {
    await page.goto('/ats-resume-checker/');
    const first = page.locator('a[href^="/ats-resume-checker/"]').first();
    const href = await first.getAttribute('href');
    const res = await page.goto(href!);
    expect(res?.status()).toBe(200);
    await checkPage(page, `role page ${href}`);
  });

  test('missing page shows the 404 page', async ({ page, guard }) => {
    guard.allowConsole.push(/status of 404/);
    const res = await page.goto('/no-such-page');
    expect(res?.status()).toBe(404);
    await checkPage(page, '404');
  });
});

test.describe('Builder stays off', () => {
  test('builder routes are 404 and the site files still load', async ({ page, guard }) => {
    guard.allowConsole.push(/status of 404/);
    const builder = await page.goto('/build');
    expect(builder?.status()).toBe(404);
    for (const path of ['/build/anything', '/static/js/builder.js', '/static/css/builder.css']) {
      expect((await page.request.get(path)).status(), path).toBe(404);
    }
    expect((await page.request.post('/api/build/create-checkout', { data: {} })).status()).toBe(404);
    for (const path of ['/static/js/app.js', '/static/css/style.css']) {
      expect((await page.request.get(path)).status(), path).toBe(200);
    }
  });
});
