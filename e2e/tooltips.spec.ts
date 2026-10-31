/**
 * Every control on the loaded page has a tooltip, and focus shows it.
 *
 * Screenshots are written for the review. They are not pixel baselines.
 */

import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

async function saveShot(page: Page, name: string): Promise<void> {
  mkdirSync("e2e/output", { recursive: true });
  const local = `e2e/output/${name}.png`;
  await page.screenshot({ path: local });
  try {
    mkdirSync("/opt/cursor/artifacts", { recursive: true });
    copyFileSync(local, `/opt/cursor/artifacts/${name}.png`);
  } catch {
    // The artifact directory is only present for the cloud review.
  }
}

test.beforeEach(async ({ page }) => {
  const html = readFileSync("static/index.html", "utf8").replace(/<script[\s\S]*?<\/script>/g, "");
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({ path: "static/tokens.css" });
  await page.addStyleTag({ path: "static/app.css" });
  await page.addScriptTag({ path: "e2e/dist/tooltips.js" });
  await page.waitForFunction(() => {
    const status = document.body.dataset.tooltips ?? "";
    if (status === "failed") throw new Error("tooltip fixture failed");
    return status === "ready";
  });
});

test("every control has a tooltip, and focus shows it", async ({ page }) => {
  const missing = await page.evaluate(() => window.tooltipAudit.missing());
  expect(missing).toEqual([]);

  const shortcuts = page.locator("#open-shortcuts");
  await shortcuts.focus();
  const tip = page.locator("#app-tooltip");
  await expect(tip).toBeVisible();
  await expect(tip).toHaveText("Show keyboard shortcuts. ?.");
  await expect(shortcuts).toHaveAttribute("aria-describedby", /app-tooltip/);
  expect(await tip.evaluate((node) => node.matches(":popover-open"))).toBe(true);
  await saveShot(page, "tooltip_shortcuts");

  await page.locator("#search").focus();
  await expect(tip).toContainText("Ctrl/Cmd+F");
  await expect(tip).toContainText("Esc");
  await expect(shortcuts).not.toHaveAttribute("aria-describedby");
  await saveShot(page, "tooltip_search");

  const loops = page.locator("#rekordbox-hot-loops");
  await loops.focus();
  await expect(loops).toHaveAttribute("aria-describedby", /rekordbox-hot-loops-help/);
  await expect(loops).toHaveAttribute("aria-describedby", /app-tooltip/);

  await page.locator(".player-wave").evaluate((node) => {
    if (node instanceof HTMLElement) node.hidden = false;
  });
  await page.locator("[aria-label='Zoom in']").focus();
  await expect(tip).toHaveText("Show a shorter stretch of the waveform around the playhead.");
  await saveShot(page, "tooltip_zoom");

  await page.locator(".player-play").focus();
  await expect(tip).toContainText("Space");
  await saveShot(page, "tooltip_play");
});

test("reduced motion shows the tooltip as soon as the pointer arrives", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.locator("#reload").hover();
  await expect(page.locator("#app-tooltip")).toBeVisible({ timeout: 150 });
  await expect(page.locator("#app-tooltip")).toHaveText("Reload the library from Serato.");
});
