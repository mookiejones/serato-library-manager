/**
 * Bundle the page and the first-run wizard.
 *
 * Both outputs are IIFEs so index.html can keep plain script tags. The
 * sourcemap sits beside each bundle. --check rebuilds in place and exits
 * non-zero when a committed bundle or map differs. esbuild is pinned in
 * package.json so the bytes stay the same on Ubuntu and Windows.
 */

import esbuild from "esbuild";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const check = process.argv.includes("--check");

const bundles = [
  { entry: "src/app.ts", outfile: "static/app.js" },
  { entry: "src/wizard-view.ts", outfile: "static/wizard.js", globalName: "SeratoWizard" },
];

const before = new Map();
if (check) {
  for (const bundle of bundles) {
    const js = join(root, bundle.outfile);
    before.set(js, readFileSync(js));
    before.set(`${js}.map`, readFileSync(`${js}.map`));
  }
}

for (const bundle of bundles) {
  await esbuild.build({
    absWorkingDir: root,
    entryPoints: [bundle.entry],
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    outfile: bundle.outfile,
    globalName: bundle.globalName,
    sourcemap: true,
    sourcesContent: true,
    legalComments: "none",
    charset: "utf8",
    logLevel: "warning",
  });
  const mapfile = join(root, `${bundle.outfile}.map`);
  const map = JSON.parse(readFileSync(mapfile, "utf8"));
  const sources = Array.isArray(map.sources) ? map.sources : [];
  if (!sources.length) {
    console.error(`${bundle.outfile}.map has no sources`);
    process.exit(1);
  }
  for (const source of sources) {
    if (typeof source !== "string" || source.includes("\\") || source.startsWith("/") || /^[A-Za-z]:/.test(source)) {
      console.error(`${bundle.outfile}.map source is not a relative forward-slash path: ${source}`);
      process.exit(1);
    }
  }
}

if (!check) {
  for (const bundle of bundles) {
    console.log(`Wrote ${bundle.outfile} and ${bundle.outfile}.map`);
  }
} else {
  for (const bundle of bundles) {
    const js = join(root, bundle.outfile);
    const map = `${js}.map`;
    const jsChanged = !before.get(js).equals(readFileSync(js));
    const mapChanged = !before.get(map).equals(readFileSync(map));
    if (jsChanged || mapChanged) {
      console.error(`${bundle.outfile} is stale. Run npm run build and commit ${bundle.outfile} and ${bundle.outfile}.map.`);
      process.exit(1);
    }
  }
}

const expectedExpectError = 0;
let expectError = 0;

function countExpectErrors(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      countExpectErrors(full);
      continue;
    }
    if (!name.endsWith(".ts")) continue;
    const text = readFileSync(full, "utf8");
    expectError += (text.match(/@ts-expect-error/g) || []).length;
    if (text.includes("@ts-nocheck") || text.includes("@ts-ignore")) {
      console.error(`${relative(root, full)} uses @ts-nocheck or @ts-ignore. Strict checking stays on.`);
      process.exit(1);
    }
  }
}

countExpectErrors(join(root, "src"));
if (expectError !== expectedExpectError) {
  console.error(`@ts-expect-error count is ${expectError}; the tracked count is ${expectedExpectError}.`);
  process.exit(1);
}
