/**
 * Screenshot the zoomed waveform and the overview with cues, a loop, and beats.
 *
 * Pixel checks use the coordinates the fixture stamps from the same mapping
 * the canvas uses. The images are the committed baselines.
 */

import { expect, test, type Page } from "@playwright/test";

test("draws cues, loops, and the beatgrid", async ({ page }) => {
  await page.setContent(
    "<!DOCTYPE html><html><head></head><body style=\"margin:0;background:#f3ecdf\"><div id=\"waveform-root\" style=\"width:800px\"></div></body></html>",
  );
  await page.addStyleTag({ path: "static/tokens.css" });
  await page.addStyleTag({ path: "static/app.css" });
  await page.addScriptTag({ path: "e2e/dist/fixture.js" });
  await page.waitForFunction(() => document.getElementById("waveform-root")?.dataset.waveformFixture === "ready");

  const detail = page.locator(".waveform-detail");
  const overview = page.locator(".waveform-overview canvas");
  const detailSample = await detail.evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext("2d");
    if (!context) return null;
    const at = (name: string, y: number): number[] => {
      const x = Number(canvas.dataset[name]);
      const pixel = context.getImageData(x, y, 1, 1).data;
      return [pixel[0] ?? 0, pixel[1] ?? 0, pixel[2] ?? 0, pixel[3] ?? 0];
    };
    return {
      cue: at("cueX", Math.floor(canvas.height / 2)),
      downbeat: at("downbeatX", 2),
      downbeatTail: at("downbeatX", 8),
      beat: at("beatX", 2),
      beatTail: at("beatX", 8),
      loop: at("loopEdgeX", Math.floor(canvas.height / 2)),
      playhead: at("playheadX", Math.floor(canvas.height / 2)),
    };
  });
  expect(detailSample).toEqual({
    cue: [204, 0, 0, 255],
    downbeat: [243, 236, 223, 255],
    downbeatTail: [243, 236, 223, 255],
    beat: [200, 187, 168, 255],
    beatTail: [35, 25, 16, 255],
    loop: [39, 170, 225, 255],
    playhead: [226, 59, 22, 255],
  });

  const overviewSample = await overview.evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext("2d");
    if (!context) return null;
    const at = (x: number): number[] => {
      const pixel = context.getImageData(x, 0, 1, 1).data;
      return [pixel[0] ?? 0, pixel[1] ?? 0, pixel[2] ?? 0, pixel[3] ?? 0];
    };
    const played = Number(canvas.dataset.playedX);
    return {
      played: at(Math.max(0, played - 4)),
      rest: at(Math.min(canvas.width - 1, played + 8)),
      cue: at(Number(canvas.dataset.cueX)),
      loop: at(Number(canvas.dataset.loopEdgeX)),
      playhead: at(played),
    };
  });
  expect(overviewSample).toEqual({
    played: [16, 11, 7, 255],
    rest: [35, 25, 16, 255],
    cue: [204, 0, 0, 255],
    loop: [39, 170, 225, 255],
    playhead: [226, 59, 22, 255],
  });

  await expect(detail).toHaveScreenshot("waveform-detail.png");
  await expect(overview).toHaveScreenshot("waveform-overview.png");
  await detail.screenshot({ path: "e2e/output/waveform-detail.png" });
  await overview.screenshot({ path: "e2e/output/waveform-overview.png" });
  await page.locator("#waveform-root").screenshot({ path: "e2e/output/waveform-with-markers.png" });

  const zoomIn = page.locator("[aria-label='Zoom in']");
  for (let step = 0; step < 3; step += 1) await zoomIn.click();
  await expect.poll(async () => page.evaluate(() => window.waveformFixture.pixelsPerSecond())).toBe(156.25);
  expect(await cueColor(page)).toEqual([204, 0, 0, 255]);
  await expect(detail).toHaveScreenshot("waveform-zoomed-in.png");
  await detail.screenshot({ path: "e2e/output/waveform-zoomed-in.png" });

  const zoomOut = page.locator("[aria-label='Zoom out']");
  for (let step = 0; step < 24 && !(await zoomOut.isDisabled()); step += 1) await zoomOut.click();
  await expect.poll(async () => page.evaluate(() => window.waveformFixture.pixelsPerSecond())).toBe(10);
  expect(await cueColor(page)).toEqual([204, 0, 0, 255]);
  await expect(detail).toHaveScreenshot("waveform-zoomed-out.png");
  await detail.screenshot({ path: "e2e/output/waveform-zoomed-out.png" });

  await page.evaluate(() => window.waveformFixture.showUnavailable());
  await expect(page.locator(".waveform-note")).toHaveText("Waveform unavailable for this format");
  await expect(page.locator(".waveform-detail-wrap")).toBeHidden();
  await page.locator("#waveform-root").screenshot({ path: "e2e/output/waveform-unavailable.png" });
});

/**
 * Read the cue color at the playhead offset for the current zoom.
 *
 * @param page Playwright page that mounted the fixture.
 * @returns RGBA of the cue column.
 */
async function cueColor(page: Page): Promise<number[]> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(".waveform-detail");
    const context = canvas?.getContext("2d");
    const pps = window.waveformFixture.pixelsPerSecond();
    if (!canvas || !context || !(canvas.clientWidth > 0)) return [];
    const scale = canvas.width / canvas.clientWidth;
    const x = Math.round((canvas.clientWidth / 2 + (9.25 - 8) * pps) * scale);
    const pixel = context.getImageData(x, Math.floor(canvas.height / 2), 1, 1).data;
    return [pixel[0] ?? 0, pixel[1] ?? 0, pixel[2] ?? 0, pixel[3] ?? 0];
  });
}
