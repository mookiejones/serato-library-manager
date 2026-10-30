/**
 * Chromium screenshots of the waveform.
 *
 * One baseline is shared. The harness draws with ImageData, and the
 * browser scale is 1, so the pixels do not depend on the operating system.
 */

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  globalSetup: "./global-setup.ts",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}{ext}",
  expect: {
    toHaveScreenshot: {
      maxDiffPixels: 0,
      animations: "disabled",
    },
  },
  use: {
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    colorScheme: "light",
  },
});
