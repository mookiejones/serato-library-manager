/**
 * Bundle the waveform fixture before Chromium opens it.
 *
 * The bundle is the page source. It is not committed.
 */

import esbuild from "esbuild";

export default async function globalSetup(): Promise<void> {
  await esbuild.build({
    entryPoints: ["e2e/fixture.ts"],
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    outfile: "e2e/dist/fixture.js",
  });
}
