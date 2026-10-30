/**
 * Screenshot the zoomed waveform and the overview with cues, a loop, and beats.
 *
 * Pixel checks use the coordinates the fixture stamps from the same mapping
 * the canvas uses. The images are the committed baselines.
 */

import { expect, test } from "@playwright/test";

test("draws cues, loops, and the beatgrid", async ({ page }) => {
  await page.setContent(
    "<!DOCTYPE html><html><head></head><body style=\"margin:0;background:#231910\"><div id=\"waveform-root\" style=\"width:800px\"></div></body></html>",
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
  await page.locator("#waveform-root").screenshot({ path: "e2e/output/waveform-with-markers.png" });
});
